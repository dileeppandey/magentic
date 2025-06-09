def enforce_role_alternation(messages):
    """Ensure messages alternate between user and assistant roles."""
    if not messages:
        return messages
    fixed = [messages[0]]
    for msg in messages[1:]:
        if msg['role'] == fixed[-1]['role']:
            if msg['role'] == 'user':
                fixed.append({'role': 'assistant', 'content': "I'm processing your request..."})
            elif msg['role'] == 'assistant':
                fixed.append({'role': 'user', 'content': "..."})
        fixed.append(msg)
    return fixed

def flatten_messages(msgs):
    out = []
    for m in msgs:
        if hasattr(m, 'content'):
            out.append(m.content)
        elif isinstance(m, dict) and 'content' in m:
            out.append(m['content'])
        else:
            out.append(str(m))
    return '\n'.join(out) 