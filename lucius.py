def get_user_input():
    """
    Function to get user input for template, persona, and description.
    If description is empty, sets it to "Generate new idea".
    
    Returns:
        tuple: (template, persona, description)
    """
    template = input("Template (For example: Product Launch - TikTok Focus) : ")
    persona = input("Persona (For example: Gen Z Urban Youth) : ")
    description = input("Description (Explain your idea. Skip if want to generate new idea) : ")
    
    # Check if description is empty
    if not description:
        description = "Generate new idea"
    
    return template, persona, description

def main():
    # Get user input
    template, persona, description = get_user_input()
    
    # Print the values
    print("Template:", template)
    print("Persona:", persona)
    print("Description:", description)

if __name__ == "__main__":
    main()
