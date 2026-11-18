"""Run this once. If you see a happy message, everything works."""
from app import llm

print("Provider:", llm.PROVIDER, "| Model:", llm.MODEL)
print("AI says:", llm.ask("Say hello in 5 words."))
print("\nSETUP OK. You are ready.")
