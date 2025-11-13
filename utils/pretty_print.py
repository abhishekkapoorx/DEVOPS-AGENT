from langchain_core.messages import convert_to_messages


def pretty_print_message(message, indent=False):
    pretty_message = message.pretty_repr(html=True)
    if not indent:
        print(pretty_message)
        return

    indented = "\n".join("\t" + c for c in pretty_message.split("\n"))
    print(indented)


def pretty_print_messages(update, last_message=False):
    """
    Pretty print all messages and updates from a LangGraph stream update.
    
    Args:
        update: Either a dict (from stream_mode="updates") or a tuple 
                (namespace, update_dict) from stream_mode="messages-tuple"
        last_message: If True, only print the last message. If False, print all messages.
    """
    is_subgraph = False
    if isinstance(update, tuple):
        ns, update = update
        # skip parent graph updates in the printouts
        if len(ns) == 0:
            return

        graph_id = ns[-1].split(":")[0]
        print(f"Update from subgraph {graph_id}:")
        print("\n")
        is_subgraph = True

    for node_name, node_update in update.items():
        update_label = f"Update from node {node_name}:"
        if is_subgraph:
            update_label = "\t" + update_label

        print(update_label)
        print("\n")

        # Handle messages if present
        if "messages" in node_update:
            messages = convert_to_messages(node_update["messages"])
            if last_message:
                messages = messages[-1:]

            for m in messages:
                pretty_print_message(m, indent=is_subgraph)
        
        # Print other state updates (tool calls, errors, etc.)
        other_updates = {k: v for k, v in node_update.items() if k != "messages"}
        if other_updates:
            for key, value in other_updates.items():
                indent_prefix = "\t" if is_subgraph else ""
                print(f"{indent_prefix}{key}: {value}")
        
        print("\n")


