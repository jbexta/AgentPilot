# Providers and Models

AgentPilot talks to AI services (OpenAI, Anthropic, Replicate, Fal, …) through a
small, uniform abstraction so the rest of the app never needs to know *how* a
given model is called. Whether something is a chat LLM, an image generator, a
speech transcriber, or a music model, it is invoked the same way:

```python
stream = await system.manager.models.run_model(model_obj=model, messages=msgs)
```

Everything below explains the three concepts that make this work — **APIs**,
**Models**, and **Providers** — how they are stored, and how to add your own.

> Implementation note: the providers/models system is **not** in `src/core`. It
> ships as part of the **`workflows` plugin** (`src/plugins/workflows`). The
> managers, the `Provider` base class, and the built-in provider modules all
> live there. This keeps the AI-serving layer fully modular and removable.


## The three concepts

| Concept      | What it is                                                                 | Stored in       | Code |
|--------------|---------------------------------------------------------------------------|-----------------|------|
| **API**      | A service / vendor and its credentials (e.g. *OpenAI*, *Replicate*).       | `apis` table    | `APIManager` |
| **Model**    | A single callable model belonging to an API (e.g. *gpt-4o*, *flux-dev*).   | `models` table  | `ModelsManager` |
| **Provider** | The Python module that knows *how* to call models for a given protocol.    | a module class  | `ProviderManager` + `Provider` subclasses |

The key distinction:

- An **API** is a row of credentials and connection config.
- A **Model** is a row that points at an API and carries that model's name,
  *kind*, default parameters, and an auto-generated parameter schema.
- A **Provider** is *code*. It is not a database row. Each model row names the
  provider plugin that should execute it (`provider_plugin` column), and the
  matching `Provider` subclass turns a request into an actual network call.

Many different APIs can be served by one provider. For example the `litellm`
provider serves OpenAI, Anthropic, Mistral, Gemini, xAI and every other vendor
LiteLLM supports — they are separate `apis` rows but all run through one
`LitellmProvider`.


## Model kinds

Every model has a `kind` that determines how it is used and which UI tab it
appears under. The kinds in use are:

- `CHAT` — text/chat LLMs (streaming completions, tool calls, structured output)
- `IMAGE` — image generation
- `VIDEO` — video generation
- `AUDIO` — audio / music generation
- `TRANSCRIPTION` — speech-to-text
- `EMBEDDING` — embeddings
- `TEXT` — generic text output (non-chat)
- `3D` — 3D asset generation

`CHAT` models are special: they stream, support tools and structured output, and
get a curated parameter form (temperature, top_p, etc.). All other kinds are
"generative media" models whose parameters are derived automatically from the
provider's OpenAPI schema and whose results are usually fetched asynchronously.


## Architecture

```
                       ┌─────────────────────────────┐
   system.manager. ───▶│ ModelsManager   (models)    │  run_model() / get_model()
                       │ APIManager      (apis)      │  credentials + config
                       │ ProviderManager (providers) │  loads Provider classes
                       └─────────────┬───────────────┘
                                     │  dispatches by model_obj['provider']
                                     ▼
                       ┌─────────────────────────────┐
                       │  Provider subclass          │  run_model(), sync_models(),
                       │  (litellm / replicate / …)  │  get_request_status/result()
                       └─────────────────────────────┘
```

### Managers

All three are `BaseManager` subclasses loaded on startup and reachable via
`system.manager.<name>`:

- **`ModelsManager`** — `src/plugins/workflows/managers/models.py`
  Loads every model joined to its API into an in-memory dict keyed by
  `(provider, kind, model_name)`. Owns the two entry points the rest of the app
  uses:
  - `get_model(model_obj)` → the merged config/parameters for a model.
  - `run_model(model_obj, **kwargs)` → resolves the provider and awaits its
    `run_model`. This is the main public API.

- **`APIManager`** — `src/plugins/workflows/managers/apis.py`
  Loads the `apis` table into a dict keyed by API name, resolving any
  environment-variable-backed keys (see *Credentials* below).

- **`ProviderManager`** — `src/plugins/workflows/managers/providers.py`
  Instantiates one object per `Providers` module and stores it under the
  module name. Also defines the **`Provider`** base class.

### Controller

`ProvidersController` (`src/plugins/workflows/controllers/providers.py`) registers
`Providers` as a module type. Provider modules are discovered from
`plugins.workflows.providers`, must inherit from `Provider`, and are
`class_based`:

```python
class ProvidersController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='providers',
            load_to_path='plugins.workflows.providers',
            class_based=True,
            inherit_from='Provider',
            description="AI model provider modules",
        )
```

Because providers are ordinary modules, you can add one simply by dropping a file
into the providers folder (or your own plugin) — see *Adding a provider*.


## Data model

### `apis` table

| Column            | Purpose                                                               |
|-------------------|-----------------------------------------------------------------------|
| `name`            | Display name of the vendor/service (e.g. `OpenAI`, `Replicate`).       |
| `client_key`      | Public/client identifier where applicable. Supports `$ENV_VAR`.       |
| `api_key`         | Secret key. Supports `$ENV_VAR` indirection. Encrypted in the UI.     |
| `config`          | JSON of API-level config merged into every model (e.g. `api_base`, `litellm_prefix`). |
| `provider_plugin` | Which provider serves this API's models.                              |
| `pinned`          | Sort priority in the UI.                                              |
| `metadata`        | Misc JSON metadata.                                                   |

### `models` table

| Column            | Purpose                                                               |
|-------------------|-----------------------------------------------------------------------|
| `api_id`          | FK to `apis.id`.                                                       |
| `name`            | Human display name (e.g. *Gpt 4o*).                                    |
| `kind`            | One of the model kinds above.                                         |
| `config`          | JSON of the model's default parameters + `_model_name` (the real id sent to the API). |
| `metadata`        | JSON; notably holds the `input_schema` used to render the parameter form. |
| `provider_plugin` | Provider module name that executes this model.                         |
| `schema_plugin`   | Optional schema override source.                                       |
| `pinned`, `ordr`  | UI ordering.                                                          |

> The actual model id sent over the wire is stored as `config._model_name`
> (older rows used `config.model_name`; both are read for compatibility). The
> `name` column is only for display.

### Credentials and `$ENV_VAR` indirection

Both `api_key` and `client_key` may be a literal value **or** a reference of the
form `$NAME`. When loaded, a `$NAME` value is resolved from the environment:

```python
if api_key.startswith('$'):
    api_key = os.environ.get(api_key[1:], '')
```

This is how the defaults work — e.g. OpenAI's key defaults to `$OPENAI_API_KEY`,
Anthropic's to `$ANTHROPIC_API_KEY`, Replicate's to `$REPLICATE_API_KEY`, etc.
(see `default_api_key_vals` in `src/utils/reset.py`). Users can override with a
literal key in the Models page.


## The `model_obj`

Everything is passed around as a plain dict (or its JSON string form) called a
**model_obj**. `convert_model_json_to_obj()` (`src/utils/helpers.py`) normalises
it and supplies a default when nothing is selected:

```python
{
    'provider':    'litellm',                      # which Provider runs it
    'kind':        'CHAT',                          # model kind
    '_model_name': 'mistral/mistral-large-latest',  # id sent to the API
    'model_params': {},                             # per-call overrides (temp, etc.)
}
```

- `provider` selects the `Provider` instance.
- `kind` + `_model_name` + `provider` form the key used to look the model's saved
  config up via `ModelsManager.get_model()`.
- `model_params` are *call-site* overrides (e.g. what the user set in the chat
  options popup); they are merged on top of the stored model config at run time.

The legacy key `model_name` is auto-migrated to `_model_name` on load.


## Providers in depth

A provider subclasses `Provider`
(`src/plugins/workflows/managers/providers.py`). The base class is small; a
provider implements only what its protocol needs.

### `run_model(model_obj, **kwargs)` — the one required method

The single abstract method. It receives a `model_obj` plus kwargs such as
`messages`, `tools`, and `stream`, and returns whatever is natural for the kind:

- **Chat providers** return an (async) streaming completion / response object.
- **Async media providers** submit the job and return a generator that yields a
  small JSON envelope with a `request_id`; the result is polled separately.

The canonical first three lines merge stored parameters onto the request:

```python
async def run_model(self, model_obj, **kwargs):
    model_obj = convert_model_json_to_obj(model_obj)
    model_s_params = system.manager.models.get_model(model_obj)         # stored config
    model_obj['model_params'] = {**model_obj.get('model_params', {}), **model_s_params}
    ...
```

### Chat extras (LiteLLM)

`LitellmProvider` (`src/plugins/workflows/providers/litellm.py`) is the workhorse
for `CHAT`. Beyond `run_model` it provides:

- **Parameter filtering** — only whitelisted keys (`temperature`, `top_p`,
  `presence_penalty`, `frequency_penalty`, `max_tokens`, plus API keys) are
  forwarded; see `ACCEPTED_KEYS` / `get_model_parameters()`.
- **Streaming + retries** — retries up to 5×, transparently falls back to
  non-streaming when a model requires org verification, and surfaces network
  errors.
- **Tool calls** — forwards `tools` and sets `tool_choice="auto"` unless a
  computer-use tool is present.
- **`get_structured_output(model_obj, **kwargs)`** — builds a dynamic Pydantic
  model from a declared schema and uses `instructor` to coerce the LLM output
  into it, returning JSON. This backs the structured-output member.

### Async media providers (Replicate / Fal / Wavespeed / Sonauto)

Media generation is long-running, so these providers split the work:

- `run_model()` submits the job and returns a generator yielding
  `{'request_id': ..., 'status': 'queued'}`.
- `get_request_status(model_name, request_id)` → normalised status dict, one of
  `{'status': 'queued'|'in_progress'|'completed'|'failed'}`.
- `get_request_result(model_name, request_id)` → `list[str]` of downloadable
  media URLs.

`Replicate` (`providers/replicate.py`) is the reference implementation, also
adding `get_result()` (streamed binary download), `get_transcription_result()`,
and `upload_file()`.

### `sync_models()` — populating the catalog

A provider may implement `sync_models()` to discover the models a service offers
and write them into the `apis`/`models` tables via `reset_table()`:

- **LiteLLM** reads `litellm.model_cost` and creates one API per
  `litellm_provider`, attaching a curated chat parameter schema.
- **Replicate** pages the Replicate REST API, reads each model's OpenAPI schema,
  infers the `kind` from the example output's media type, and converts the input
  schema into a parameter form.

`scrape_models()` and `reset_models()` in `src/utils/reset.py` orchestrate this:
the *Sync models* button on the Models page (or a fresh install) calls every
provider's `sync_models()` and rebuilds the catalog, **preserving user API keys**.

### OpenAPI → parameter schema conversion

For non-chat models the parameter form is generated from the service's OpenAPI
schema. The base `Provider` class does the heavy lifting:

- `resolve_schema()` (provider-specific) flattens `$ref` / `anyOf` / `oneOf` /
  `allOf` and reports nullability.
- `convert_openapi_property()` maps an OpenAPI property to an AgentPilot field
  schema dict: it maps types (`string`→`text`, `number`→`float`, `array`→`list`,
  enum→tuple/combo), auto-detects media-upload fields (URI format or
  image/video/audio titles), promotes `prompt`/`lyrics` fields to multi-line
  XML-highlighted editors, and carries through defaults, min/max, tooltips and
  optional toggles.
- `convert_all_openapi_properties()` runs this over every property and lays out
  rows.

The resulting list is stored as `models.metadata.input_schema` and fed straight
into a `ConfigFields` widget to render the model's parameters — no hand-written
UI per model.

### Built-in providers

| Provider     | Module                              | Kinds served            | Notes |
|--------------|-------------------------------------|-------------------------|-------|
| `litellm`    | `providers/litellm.py`              | `CHAT` (all LLM vendors) | Streaming, tools, structured output. |
| `replicate`  | `providers/replicate.py`            | image/video/audio/text  | Async polling, OpenAPI schema, file upload. |
| `fal`        | `providers/fal.py`                  | generative media        | Async polling. |
| `wavespeed`  | `providers/wavespeed.py`            | generative media        | Async polling. |
| `sonauto`    | `providers/sonauto.py`              | audio / music           | Async polling. |


## How a model gets called (end to end)

1. A widget holds a `model_obj` (chosen via a `ModelComboBox`).
2. It calls `system.manager.models.run_model(model_obj=..., messages=...)`.
3. `ModelsManager.run_model` resolves `system.manager.providers.get(provider)`
   and awaits `provider.run_model(...)`.
4. The provider merges stored params (`models.get_model`) with call-site
   `model_params`, calls the service, and returns a stream / request envelope.
5. For chat, the caller iterates the stream. For async media, a separate loop
   polls `get_request_status` then `get_request_result`.

Real consumers include the chat member (`plugins/workflows/members/__init__.py`),
the structured-output member, `GenerateWidget`, `ChatWidget`, and various Studio
audio operations.


## The GUI

### Models page

`Page_Models_Settings` (`src/plugins/workflows/pages/models.py`) is a
`ConfigDBTree` over the `apis` table. The left tree lists APIs (with their key
fields editable inline, key encrypted); the right panel is a tabbed widget:

- An outer tab per **kind** (Chat, Video, Image, Audio, Text, 3D) — only the
  kinds the selected API actually has are shown.
- Inside each kind, a **Models** sub-tree (the individual models) and a **Config**
  tab. Selecting a model loads its `metadata.input_schema` into a `ConfigFields`
  form plus a `MultiPreview`/`GenerateWidget` for test generations.

The **Sync models** button runs `reset_models()` then reloads the API, provider
and every `ModelComboBox` in the app.

### Model field

`ModelComboBox` (`src/gui/fields/model.py`) is the reusable model picker used
everywhere a model is selected. Key points:

- Construct with `model_kind='CHAT'` (or another kind, or `'ALL'`) to filter the
  list; chat-only mode also hides APIs that have no key set.
- The dropdown is grouped by API name (bold, disabled header rows).
- Its value **is** a `model_obj` (`get_value()`/`set_value()`), with the
  attached parameter form's values folded into `model_params`.
- When empty it falls back to the configured default
  (`system.default_<kind>_model`).
- For non-chat kinds it builds its parameter form dynamically from the selected
  model's `metadata.input_schema`; for chat it shows the curated `PopupModel`.

> ⚠️ The file carries prominent warnings: do **not** set breakpoints inside
> `ModelComboBox.get_value()` / the combo paint path — a PySide combobox bug can
> freeze the IDE/desktop on Linux.


## Adding a provider

1. **Create the module.** Add a file under
   `src/plugins/workflows/providers/` (or under `providers/` in your own plugin),
   containing a class that inherits from `Provider`. If the file declares more
   than one class, mark yours with `@set_module_type(module_type='Providers')`.

   ```python
   from plugins.workflows.managers.providers import Provider
   from utils.helpers import set_module_type, convert_model_json_to_obj
   from gui import system

   @set_module_type(module_type='Providers')
   class MyProvider(Provider):
       async def run_model(self, model_obj, **kwargs):
           model_obj = convert_model_json_to_obj(model_obj)
           params = system.manager.models.get_model(model_obj)
           # ... call your service, return a stream or a request envelope ...
   ```

2. **Implement what your kind needs.**
   - Chat: return a streaming completion; optionally add `get_structured_output`.
   - Async media: return a `{'request_id': ...}` generator and implement
     `get_request_status` / `get_request_result`.

3. **(Optional) Implement `sync_models()`** to auto-populate the catalog. Use
   `reset_table('apis', ...)` then `reset_table('models', ...)`, setting each
   model's `provider_plugin` to your module name and storing an `input_schema` in
   `metadata` (the base `convert_*_openapi_*` helpers can build it for you).

4. The module name becomes the provider key. Any `models` row whose
   `provider_plugin` equals that name will be executed by your provider.

## Adding a single model manually

You don't have to write code to add a model — in the **Models** page pick (or add)
an API, choose the kind tab, click **Add Model**, set its **Model name**
(`_model_name`, the id sent to the service), and fill in parameters. As long as
the API's `provider_plugin` points at a provider that understands that
`_model_name`, it is immediately usable from any `ModelComboBox`.
