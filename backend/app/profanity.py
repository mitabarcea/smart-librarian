from better_profanity import profanity
profanity.load_censor_words()

def is_clean(text: str) -> bool:
    return not profanity.contains_profanity(text or "")
