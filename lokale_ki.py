"""Terminal client using exactly the same retrieval and prompt as the web app."""
import os
import sys
from server import Backend, _messages, parse_ai_response
from rag_engine import NOT_IN_MANUAL


def main():
    backend = Backend()
    def answer(question):
        context, grounded, reference = backend.retrieve(question, os.getenv("RETRIEVAL_MODE", "hybrid"))
        if not grounded:
            print(NOT_IN_MANUAL)
            return
        response = backend.answer(_messages(question, context))
        summary, body, _ = parse_ai_response(response.choices[0].message.content or "")
        print(f"{summary}\n\n{body}\n\nQuelle: {reference}")
    if len(sys.argv) > 1:
        answer(" ".join(sys.argv[1:]))
        return
    while True:
        try:
            question = input("Frage (leer beendet): ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            break
        answer(question)


if __name__ == "__main__":
    main()
