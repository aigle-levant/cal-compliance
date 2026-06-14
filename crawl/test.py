import requests

url = "https://dir.ca.gov/t8/9794.html"

r = requests.get(url, timeout=30)

print(r.status_code)
print(len(r.text))