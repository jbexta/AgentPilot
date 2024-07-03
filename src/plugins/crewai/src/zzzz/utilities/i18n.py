import json
import os
from typing import Dict, Optional

from pydantic import BaseModel, Field, PrivateAttr, ValidationError, model_validator

langs = {
    'en': {
        "slices": {
            "observation": "\nObservation",
            "task": "Begin! This is VERY important to you, your job depends on it!\n\nCurrent Task: {input}",
            "memory": "This is the summary of your work so far:\n{chat_history}",
            "role_playing": "You are {role}.\n{backstory}\n\nYour personal goal is: {goal}",
            "tools": "TOOLS:\n------\nYou have access to only the following tools:\n\n{tools}\n\nTo use a tool, please use the exact following format:\n\n```\nThought: Do I need to use a tool? Yes\nAction: the action to take, should be one of [{tool_names}], just the name.\nAction Input: the input to the action\nObservation: the result of the action\n```\n\nWhen you have a response for your task, or if you do not need to use a tool, you MUST use the format:\n\n```\nThought: Do I need to use a tool? No\nFinal Answer: [your response here]",
            "task_with_context": "{task}\nThis is the context you're working with:\n{context}"
        },
        "errors": {
            "used_too_many_tools": "I've used too many tools for this task. I'm going to give you my absolute BEST Final answer now and not use any more tools.",
            "agent_tool_missing_param": "\nError executing tool. Missing exact 3 pipe (|) separated values. For example, `coworker|task|context`. I need to make sure to pass context as context.\n",
            "agent_tool_unexsiting_coworker": "\nError executing tool. Co-worker mentioned on the Action Input not found, it must to be one of the following options: {coworkers}.\n",
            "task_repeated_usage": "I just used the {tool} tool with input {tool_input}. So I already know the result of that and don't need to use it now.\n"
        },
        "tools": {
            "delegate_work": "Useful to delegate a specific task to one of the following co-workers: {coworkers}.\nThe input to this tool should be a pipe (|) separated text of length 3 (three), representing the co-worker you want to ask it to (one of the options), the task and all actual context you have for the task.\nFor example, `coworker|task|context`.",
            "ask_question": "Useful to ask a question, opinion or take from on of the following co-workers: {coworkers}.\nThe input to this tool should be a pipe (|) separated text of length 3 (three), representing the co-worker you want to ask it to (one of the options), the question and all actual context you have for the question.\n For example, `coworker|question|context`."
        }
    },
    'el': {
        "slices": {
            "observation": "\nΠαρατήρηση",
            "task": "Αρχή! Αυτό είναι ΠΟΛΥ σημαντικό για εσάς, η δουλειά σας εξαρτάται από αυτό!\n\nΤρέχουσα εργασία: {input}",
            "memory": "Αυτή είναι η περίληψη της μέχρι τώρα δουλειάς σας:\n{chat_history}",
            "role_playing": "Είσαι {role}.\n{backstory}\n\nΟ προσωπικός σας στόχος είναι: {goal}",
            "tools": "ΕΡΓΑΛΕΙΑ:\n------\nΈχετε πρόσβαση μόνο στα ακόλουθα εργαλεία:\n\n{tools}\n\nΓια να χρησιμοποιήσετε ένα εργαλείο, χρησιμοποιήστε την ακόλουθη ακριβώς μορφή:\n\n```\nΣκέψη: Χρειάζεται να χρησιμοποιήσω κάποιο εργαλείο; Ναί\nΔράση: η ενέργεια που πρέπει να γίνει, πρέπει να είναι μία από τις[{tool_names}], μόνο το όνομα.\nΕνέργεια προς εισαγωγή: η είσοδος στη δράση\nΠαρατήρηση: το αποτέλεσμα της δράσης\n```\n\nΌταν έχετε μια απάντηση για την εργασία σας ή εάν δεν χρειάζεται να χρησιμοποιήσετε ένα εργαλείο, ΠΡΕΠΕΙ να χρησιμοποιήσετε τη μορφή:\n\n```\nΣκέψη: Χρειάζεται να χρησιμοποιήσω κάποιο εργαλείο; Οχι\nΤελική απάντηση: [η απάντησή σας εδώ]",
            "task_with_context": "{task}\nΑυτό είναι το πλαίσιο με το οποίο εργάζεστε:\n{context}"
        },
        "errors": {
            "used_too_many_tools": "Έχω χρησιμοποιήσει πάρα πολλά εργαλεία για αυτήν την εργασία. Θα σας δώσω την απόλυτη ΚΑΛΥΤΕΡΗ τελική μου απάντηση τώρα και δεν θα χρησιμοποιήσω άλλα εργαλεία.",
            "agent_tool_missing_param": "\nΣφάλμα κατά την εκτέλεση του εργαλείου. Λείπουν ακριβώς 3 διαχωρισμένες τιμές σωλήνων (|). Για παράδειγμα, `coworker|task|context`. Πρέπει να φροντίσω να περάσω το πλαίσιο ως πλαίσιο.\n",
            "agent_tool_unexsiting_coworker": "\nΣφάλμα κατά την εκτέλεση του εργαλείου. Ο συνάδελφος που αναφέρεται στο Ενέργεια προς εισαγωγή δεν βρέθηκε, πρέπει να είναι μία από τις ακόλουθες επιλογές: {coworkers}.\n",
            "task_repeated_usage": "Μόλις χρησιμοποίησα το {tool} εργαλείο με είσοδο {tool_input}. Άρα ξέρω ήδη το αποτέλεσμα αυτού και δεν χρειάζεται να το χρησιμοποιήσω τώρα.\n"
        },
        "tools": {
            "delegate_work": "Χρήσιμο για την ανάθεση μιας συγκεκριμένης εργασίας σε έναν από τους παρακάτω συναδέλφους: {coworkers}.\nΗ είσοδος σε αυτό το εργαλείο θα πρέπει να είναι ένα κείμενο χωρισμένο σε σωλήνα (|) μήκους 3 (τρία), που αντιπροσωπεύει τον συνάδελφο στον οποίο θέλετε να του ζητήσετε (μία από τις επιλογές), την εργασία και όλο το πραγματικό πλαίσιο που έχετε για την εργασία .\nΓια παράδειγμα, `coworker|task|context`.",
            "ask_question": "Χρήσιμο για να κάνετε μια ερώτηση, γνώμη ή αποδοχή από τους παρακάτω συναδέλφους: {coworkers}.\nΗ είσοδος σε αυτό το εργαλείο θα πρέπει να είναι ένα κείμενο χωρισμένο σε σωλήνα (|) μήκους 3 (τρία), που αντιπροσωπεύει τον συνάδελφο στον οποίο θέλετε να το ρωτήσετε (μία από τις επιλογές), την ερώτηση και όλο το πραγματικό πλαίσιο που έχετε για την ερώτηση.\nΓια παράδειγμα, `coworker|question|context`."
        }
    }
}

class I18N(BaseModel):
    _translations: Optional[Dict[str, str]] = PrivateAttr()
    language: Optional[str] = Field(
        default="en",
        description="Language used to load translations",
    )

    @model_validator(mode="after")
    def load_translation(self) -> "I18N":
        """Load translations from a JSON file based on the specified language."""
        try:
            self._translations = langs[self.language]
        except FileNotFoundError:
            raise ValidationError(
                f"Trasnlation file for language '{self.language}' not found."
            )
        except json.JSONDecodeError:
            raise ValidationError(f"Error decoding JSON from the prompts file.")
        return self

    def slice(self, slice: str) -> str:
        return self.retrieve("slices", slice)

    def errors(self, error: str) -> str:
        return self.retrieve("errors", error)

    def tools(self, error: str) -> str:
        return self.retrieve("tools", error)

    def retrieve(self, kind, key):
        try:
            return self._translations[kind].get(key)
        except:
            raise ValidationError(f"Translation for '{kind}':'{key}'  not found.")
