import redis
import json
from openai import OpenAI
from decouple import Config, Csv, config

# Initialize OpenAI client (replace with your API key)
client = OpenAI(api_key=config('API_KEY'))

# Initialize Redis connection (adjust host, port, password as needed)
redis_client = redis.Redis(
    host= config('DB_HOST'),
    port=config('DB_PORT'),
    password=config('DB_PASSWORD'),  # Set password if required
    decode_responses=True  # Return strings instead of bytes
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

# Main CLI loop
def main():
    print("Connected to Redis database.")
    print("Schema:")
    print(schema_string)
    print("\nAsk a question about the database (type 'exit' to quit):")

    messages = [
        {"role": "system", "content": f"You are a helpful assistant with access to a Redis database with hash keys. Use query_redis to answer database questions. Schema:\n{schema_string}"}
    ]

    while True:
        # Get user input
        prompt = input("> ")
        if prompt.lower() == "exit":
            print("Goodbye!")
            break
        
        # Add user message
        messages.append({"role": "user", "content": prompt})
        
        try:
            # First API call: Get tool call if needed
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )

            response_message = response.choices[0].message
            
            # Check for tool calls
            if hasattr(response_message, 'tool_calls') and response_message.tool_calls:
                tool_call = response_message.tool_calls[0]
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                query_str = arguments.get("query")

                if function_name == "query_redis" and query_str:
                    # Execute Redis query
                    result = query_redis(redis_client, query_str)
                    
                    # Append assistant message with tool call
                    messages.append({
                        "role": "assistant",
                        "content": None,  # No content, just tool calls
                        "tool_calls": [tool_call.model_dump()]  # Convert to dict
                    })
                    
                    # Append tool response
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": result
                    })
                    
                    # Second API call: Get final plain-text response
                    final_response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=messages
                    )
                    final_message = final_response.choices[0].message.content
                    print(final_message)
                    messages.append({"role": "assistant", "content": final_message})
                else:
                    print(f"Error: Unknown function '{function_name}' or missing query")
            else:
                # No tool call, direct response
                print(response_message.content)
                messages.append({"role": "assistant", "content": response_message.content})

        except Exception as e:
            print(f"An error occurred: {str(e)}")
            # Reset messages to system message on error to avoid malformed state
            messages = messages[:1]

if __name__ == "__main__":
    main()