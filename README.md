# Chat with Redis
### If you are looking for a Redis interpreter can speak in natural language, you can use this app to implement it.



#### Let's see how does it works


**Requirements**

- Python 3.10
- OpenAI key
- Redis database up&runnig


**Install python modules**
```bash
pip install openai redis python-decouple
```


**Configure .env parameters**
```html
API_KEY='ENTER-YOUR-AI-API-KEY-HERE'
DB_HOST='ENTER-YOUR-REDIS-HOST'
DB_PORT='ENTER-YOUR-REDIS-PORT'
DB_PASSWORD='ENTER-YOUR-REDIS-PASSWORD'
```


**Run the code**
```bash
python app.py
```

