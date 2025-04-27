#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import requests

def load_config():
    """加载配置文件"""
    with open('config.json', 'r') as f:
        return json.load(f)

def check_inventory():
    """检查闪邮箱库存"""
    try:
        api_url = "https://zizhu.shanyouxiang.com/kucun"
        
        print(f"正在调用API: {api_url}")
        response = requests.get(api_url)
        
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"库存信息: outlook - {data.get('outlook', 0)}, hotmail - {data.get('hotmail', 0)}")
            return data
        
        return {"hotmail": 0, "outlook": 0}
    except Exception as e:
        print(f"查询库存失败: {e}")
        return {"hotmail": 0, "outlook": 0}

def check_balance(card_number):
    """检查闪邮箱卡余额"""
    try:
        api_url = "https://zizhu.shanyouxiang.com/yue"
        params = {"card": card_number}
        
        print(f"正在调用API: {api_url}")
        print(f"参数: {params}")
        
        response = requests.get(api_url, params=params)
        
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"余额: {data.get('num', 0)}")
            return data.get('num', 0)
        
        return 0
    except Exception as e:
        print(f"查询余额失败: {e}")
        return 0

def test_extract_emails(card_number, count=1, email_type="outlook"):
    """测试提取邮箱"""
    try:
        api_url = "https://zizhu.shanyouxiang.com/huoqu"
        params = {
            "card": card_number,
            "shuliang": count,
            "leixing": email_type
        }
        
        print(f"正在调用API: {api_url}")
        print(f"参数: {params}")
        
        response = requests.get(api_url, params=params)
        
        print(f"状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            email_text = response.text.strip()
            if email_text:
                emails = []
                for line in email_text.split('\n'):
                    # 使用"----"分割，但只取前两部分（邮箱和密码）
                    parts = line.split('----')
                    if len(parts) >= 2:
                        email = parts[0].strip()
                        password = parts[1].strip()
                        emails.append({
                            "email": email, 
                            "password": password
                        })
                        
                print(f"成功提取 {len(emails)} 个邮箱:")
                for i, email_data in enumerate(emails):
                    print(f"{i+1}. {email_data['email']} - {email_data['password']}")
                return emails
        
        print("提取邮箱失败或返回数据格式不正确")
        return []
    except Exception as e:
        print(f"提取邮箱失败: {e}")
        return []

if __name__ == "__main__":
    config = load_config()
    card_number = config['email_extraction']['card_number']
    email_type = config['email_extraction'].get('email_type', 'outlook')
    
    print("="*50)
    print("测试闪邮箱库存API")
    check_inventory()
    
    print("\n" + "="*50)
    print("测试闪邮箱余额API")
    check_balance(card_number)
    
    print("\n" + "="*50)
    print("测试提取邮箱API (仅提取1个)")
    test_extract_emails(card_number, 1, email_type) 