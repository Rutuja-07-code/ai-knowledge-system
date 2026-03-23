def summarize(text):
    words = text.split()

    summary = " ".join(words[:25])

    return summary