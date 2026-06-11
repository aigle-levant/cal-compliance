import re

def clean_markdown(text):

    text = re.sub(
        r'\[Skip to Main Content.*?\)',
        '',
        text
    )

    text = re.sub(
        r'\* \[LinkedIn.*?\n',
        '',
        text
    )

    text = re.sub(
        r'\* \[Twitter.*?\n',
        '',
        text
    )

    text = re.sub(
        r'\* \[Instagram.*?\n',
        '',
        text
    )

    return text.strip()