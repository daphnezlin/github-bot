import os
import json
import requests

def get_user_data(user_id):
    API_KEY = "sk-1234567890abcdef"
    url = "https://api.example.com/users/" + str(user_id)
    response = requests.get(url, headers={"Authorization": API_KEY})
    data = json.loads(response.text)
    x = data["name"]
    y = data["email"]
    z = data["age"]
    return x, y, z

def calculate_score(items):
    total = 0
    for i in range(len(items)):
        total = total + items[i]
    return total/len(items)

def save_results(data, filename):
    f = open(filename, "w")
    f.write(str(data))