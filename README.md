# Chat with Redis
#### In this project you will be able to connect to your Redis database and query all data using a natural language prompt! This application has been tested over GTP-4o LLM using an OpenAI key. I also tested other smaller LLM such as GPT-4o-mini but the response quality is not enogh to get a valid query. 



**Requirements**

- Python 3.10
- OpenAI key
- Your Redis database already up&runnig


**Install python modules**
```bash
pip install openai redis python-decouple
```


**Configure .env parameters**
*API_KEY='ENTER-YOUR-AI-API-KEY-HERE'*
*DB_HOST='ENTER-YOUR-REDIS-HOST'*
*DB_PORT='ENTER-YOUR-REDIS-PORT'*
*DB_PASSWORD='ENTER-YOUR-REDIS-PASSWORD'*




**Run the code**
```bash
streamlit run app.py
```

![alt text](redischat.png)

### Let see how does the code work

**STEP1.** First of all we need to retrieve all Redis schema information. With the following method we are able get the whole redis schema to submit to LLM. In this way the GTP-4o LLM will be able to understand where it needs to jump into before preparing a query.

```python
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

```


**STEP2.** Define the tool for querying Redis. This is the part where define the function ***query_redis*** along with Redis schema to send to GTP-4o LLM. Take a look that here we are creating a AI agent that is able to decide if the rensponse is a possibile query to run on Redis or not. So it's crucial to properly formulate how it should elaborate the input information before the next step.

```python
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
```

**STEP3.** This method is invoked when the LLM provide a valid query to submit to Redis database  

```python
# Step 3. Function to query Redis
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
```

**Step4.** In the main we will use Streamlit as user interface and chat.completion API to ask LLM to check if the user request could be a Redis query and if so to execute it. As you can see in the following code excerpt the ***client.chat.completions.create*** method is invoked twice. The first time is to ask LLM to check if the response can be formulated through the AI function query_redis. Next, the LLM is invoked one more time to ask if is needed further LLM reasoning to arrange the final response (e.g. special formatting, to do some consideration about the query output).
```python
def main():
...
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

...
```
