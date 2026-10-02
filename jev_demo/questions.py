"""The typed questions, in the exact shape that goes on the wire.

Three primitives, one request, all evaluated in parallel over the same state:

  Noul   -> a probability that a statement is true
  Choice -> one label from a set you define, plus probabilities and confidence
  Score  -> a position on ordered levels you define

The SDK takes these dictionaries as-is; `Choice(...)`, `Noul(...)` and
`Score(...)` objects are an editor-friendly equivalent of the same thing.
"""

QUESTIONS_DICT = {
    "risk": {
        "type": "choice",
        "instructions": "Which bucket does the command in `command` belong to?",
        "criteria": {
            "read_only": "Only inspects cluster or host state and changes nothing",
            "mutating": "Creates, changes, scales or restarts something that can be undone",
            "destructive": "Deletes data, evicts workloads or removes state that cannot be undone",
            "unknown": "Not enough information in the state to tell",
        },
    },
    "data_loss": {
        "type": "noul",
        "instructions": "Could this command permanently lose data, such as deleting a volume, "
        "dropping a database, or removing objects that cannot be recreated?",
    },
    "blast_radius": {
        "type": "score",
        "instructions": "How many workloads does this command disrupt at once?",
        "criteria": [
            "One pod or one resource only",
            "One service, or several pods of that service",
            "A node, several services, or an entire namespace",
            "The whole cluster",
        ],
    },
}
