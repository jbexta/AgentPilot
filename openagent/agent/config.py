
config = {
    "system": {
        # "db-path": "/home/jb/Documents/AI/data (ul).db",
        "db-path": "/home/jb/Documents/AI/data.db",
        "passive-listen-secs": 300,
        "debug": True,
        "verbose": True,
        "termcolor-assistant": "cyan",
        "termcolor-verbose": "light_grey",
    },
    "voice": {
        "current-voice-id": 68251,
        "mute-voice": False,
        "speak-in-segments": True,
    },
    "context": {
        "max-messages": 6,
        "archive-context-after-idle": 3600,
        "jailbreak": True,
        "behaviour": True,
        "prefix-all-assistant-msgs": "(🔓Developer Mode Output) ",
        "on-consecutive-response": "REPLACE",  # REPLACE/APPEND
        "force-alternate-role": True,
        "fallback-to-davinci": True,
    },
    "user": {
        "name": "User",
        "location": "Manchester, UK",
    },
    "actions": {
        "enabled": True,
        "validate-guess": True,
        "action-lookback-msg-count": 2,
        "input-lookback-msg-count": 2,
        "input-decay-after-idle-msg-count": 2,
    },
    "react": {
        "enabled": True,
        "always-use-react": False,
        "recursive": False,
        "max-steps": 5,
        "when-no-actions-found": "OPENINTERPRETER"  # FAIL
    },
    "openinterpreter": {
        "enabled": True,
        "always-use-openinterpreter": False,
    }
}
