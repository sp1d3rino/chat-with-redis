import streamlit as st
import redis
import json
from openai import OpenAI
from decouple import Config, Csv, config

# Initialize OpenAI client
client = OpenAI(api_key=config('API_KEY'))

# Initialize Redis connection
redis_client = redis.Redis(
    host=config('DB_HOST'),
    port=config('DB_PORT'),
    password=config('DB_PASSWORD'),
    decode_responses=True
)

# Function to get schema of hash keys
def get_redis_hash_schema(redis_client):
    """Retrieve all hash keys and their fields from Redis."""
    all_keys = redis_client.keys("*")
    schema = []
    for key in all_keys:
        if redis_client.type(key) == "hash":
            fields = redis_client.hkeys(key)
            schema.append({"key_name": key, "fields": fields})
    return schema

# Build schema string for the AI
schema_dict = get_redis_hash_schema(redis_client)
schema_string = "\n".join(
    [f"Hash Key: {entry['key_name']} (Fields: {', '.join(entry['fields'])})"
     for entry in schema_dict]
)

# Define the tool for querying Redis
tools = [
    {
        "type": "function",
        "function": {
            "name": "query_redis",
            "description": """
                Query the Redis database for hash keys. Provide a 'query' JSON string.
                Use 'key' for the hash key name and optional 'field' for a specific field.
                Examples: '{"key": "user:1"}' (all fields), '{"key": "user:1", "field": "age"}' (specific field).
            """,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": f"""
                            JSON string for the query.
                            Format: '{{"key": "key_name", "field": "field_name"}}' (field optional).
                            Schema: {schema_string}
                        """,
                    }
                },
                "required": ["query"],
            },
        }
    }
]

# Function to query Redis
def query_redis(redis_client, query_str: str) -> str:
    """Query Redis hash keys and return plain text result."""
    try:
        query_dict = json.loads(query_str)
        if "key" not in query_dict:
            return "Error: 'key' is missing in query"
        
        key = query_dict["key"]
        key_type = redis_client.type(key)
        
        if key_type != "hash":
            return f"Error: '{key}' is not a hash key (type: {key_type})"
        
        if "field" in query_dict:
            field = query_dict["field"]
            value = redis_client.hget(key, field)
            if value is None:
                return f"No value found for field '{field}' in key '{key}'"
            return f"{field}: {value}"
        else:
            fields = redis_client.hgetall(key)
            if not fields:
                return f"No fields found in key '{key}'"
            return "\n".join([f"{k}: {v}" for k, v in fields.items()])
    
    except json.JSONDecodeError as e:
        return f"Error: Invalid query format - {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

# Streamlit App
def main():
    # Load external CSS
    with open("style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

    # Header
    st.markdown("<h1 class='title'>Redis Chat</h1>", unsafe_allow_html=True)

    # Sidebar with schema
    with st.sidebar:
        st.info("Connected to Redis database.")

    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "system", "content": f"You are a helpful assistant with access to a Redis database with hash keys. Use query_redis to answer database questions. Schema:\n{schema_string}"}
        ]
    if "last_prompt" not in st.session_state:
        st.session_state.last_prompt = None

    # Chat container
    chat_container = st.container()
    with chat_container:
        st.markdown("<div class='chat-container'>", unsafe_allow_html=True)
        for msg in st.session_state.messages[1:]:  # Skip system message
            if msg["role"] == "user":
                st.markdown(f"<div class='user-message'>{msg['content']}</div>", unsafe_allow_html=True)
            elif msg["role"] == "assistant" and msg.get("content"):
                st.markdown(f"<div class='assistant-message'>{msg['content']}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # User input with form to control submission
    with st.form(key="input_form", clear_on_submit=True):
        prompt = st.text_input("Ask a question about the database...", key="prompt_input")
        col1, col2 = st.columns([3, 1])
        with col2:
            submit_button = st.form_submit_button(label="Send")
        with col2:
            clear_button = st.form_submit_button(label="Clear Chat")

    # Process new prompt only on submit and if different from last prompt
    if submit_button and prompt and prompt != st.session_state.last_prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.last_prompt = prompt  # Store the last processed prompt
        
        with st.spinner("Processing..."):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=st.session_state.messages,
                    tools=tools,
                    tool_choice="auto"
                )
                response_message = response.choices[0].message
                
                if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
                    tool_call = response_message.tool_calls[0]
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    query_str = arguments.get("query")

                    if function_name == "query_redis" and query_str:
                        result = query_redis(redis_client, query_str)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call.model_dump()]
                        })
                        st.session_state.messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": result
                        })
                        final_response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=st.session_state.messages
                        )
                        final_message = final_response.choices[0].message.content
                        st.session_state.messages.append({"role": "assistant", "content": final_message})
                    else:
                        st.error(f"Error: Unknown function '{function_name}' or missing query")
                else:
                    st.session_state.messages.append({"role": "assistant", "content": response_message.content})

            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                st.session_state.messages = st.session_state.messages[:1]

        # Rerun to update display after processing
        st.rerun()

    # Clear chat history
    if clear_button:
        st.session_state.messages = [
            {"role": "system", "content": f"You are a helpful assistant with access to a Redis database with hash keys. Use query_redis to answer database questions. Schema:\n{schema_string}"}
        ]
        st.session_state.last_prompt = None
        st.rerun()

if __name__ == "__main__":
    main()