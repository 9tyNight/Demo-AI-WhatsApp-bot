from ai_agent import run_agent


def main() -> None:
    print("WhatsApp/Odoo AI Support Demo")
    print("Try: 'Do you have French press in stock?'")
    print("Try: 'Any promotions on chargers?'")
    print("Try: 'I am angry, connect me to a human'")
    print("Type 'exit' to quit.\n")

    while True:
        user_message = input("Customer: ").strip()
        if user_message.lower() in {"exit", "quit"}:
            break

        result = run_agent(user_message)
        print(f"\nBot: {result.reply}")
        print(f"Handoff required: {result.human_handoff}")
        print(f"Tool trace: {result.tool_calls}\n")


if __name__ == "__main__":
    main()
