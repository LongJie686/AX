import requests
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "twitter154.p.rapidapi.com")
TWITTER_USERNAME = os.getenv("TWITTER_USERNAME", "zksdog")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "1"))

if not RAPIDAPI_KEY:
	raise ValueError("RAPIDAPI_KEY 未配置，请在 .env 文件中设置")
if not FEISHU_WEBHOOK_URL:
	raise ValueError("FEISHU_WEBHOOK_URL 未配置，请在 .env 文件中设置")

while True:
	# rapidapi接口
	url = f"https://{RAPIDAPI_HOST}/user/details"

	# 查询参数
	querystring = {"username": TWITTER_USERNAME}

	# 请求头
	headers = {
		"X-RapidAPI-Key": RAPIDAPI_KEY,
		"X-RapidAPI-Host": RAPIDAPI_HOST,
	}

	response = requests.get(url, headers=headers, params=querystring)

	# 拿到接口返回的数据
	print(response.json())

	name = response.json()["name"]
	location = response.json()["location"]
	description = response.json()["description"]

	# 将接口返回的数据拼接
	message = {
		"msg_type": "text",
		"content": {
			"text": f"昵称: {name}\n位置: {location}\n简介: {description}\n"
		},
	}

	# 将我们想要的数据推送到飞书频道
	requests.post(
		FEISHU_WEBHOOK_URL,
		headers={"Content-Type": "application/json"},
		data=json.dumps(message),
	)
	time.sleep(POLL_INTERVAL)
