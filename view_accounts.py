#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import psycopg2
from tabulate import tabulate

def load_config():
    """加载配置文件"""
    with open('config.json', 'r') as f:
        return json.load(f)

def view_registered_accounts():
    """查看已注册的账号信息"""
    config = load_config()
    conn_string = config['database']['connection_string']
    
    # 连接数据库
    conn = None
    try:
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()
        
        # 查询已注册的账号信息
        query = """
        SELECT r.id, e.email, r.pikpak_username, r.pikpak_password, 
               r.user_id, r.register_time, r.status
        FROM registrations r
        JOIN emails e ON r.email_id = e.id
        WHERE r.status = 'success'
        ORDER BY r.register_time DESC
        LIMIT 100
        """
        
        cursor.execute(query)
        accounts = cursor.fetchall()
        
        if not accounts:
            print("没有找到已注册的账号")
            return
        
        # 使用tabulate格式化输出
        headers = ["ID", "邮箱", "用户名", "密码", "用户ID", "注册时间", "状态"]
        print(tabulate(accounts, headers=headers, tablefmt="pretty"))
        
        # 询问是否查看完整账号信息
        account_id = input("\n输入要查看完整信息的账号ID (直接回车退出): ")
        if account_id and account_id.isdigit():
            view_complete_account_info(conn, int(account_id))
        
    except Exception as e:
        print(f"查询账号信息失败: {e}")
    finally:
        if conn:
            conn.close()

def view_complete_account_info(conn, account_id):
    """查看指定账号的完整信息"""
    try:
        cursor = conn.cursor()
        query = """
        SELECT r.account_data
        FROM registrations r
        WHERE r.id = %s
        """
        
        cursor.execute(query, (account_id,))
        result = cursor.fetchone()
        
        if not result or not result[0]:
            print(f"未找到ID为 {account_id} 的账号完整信息")
            return
        
        account_data = result[0]
        print("\n完整账号信息:")
        print(json.dumps(account_data, indent=2, ensure_ascii=False))
        
        # 查看是否有本地保存的账号文件
        if "name" in account_data:
            filename = f"account/{account_data['name']}.json"
            if os.path.exists(filename):
                print(f"\n本地账号文件位置: {filename}")
        
    except Exception as e:
        print(f"查询完整账号信息失败: {e}")

def view_local_account_files():
    """查看本地账号文件"""
    account_dir = "account"
    if not os.path.exists(account_dir):
        print("账号目录不存在")
        return
    
    account_files = [f for f in os.listdir(account_dir) if f.endswith(".json")]
    if not account_files:
        print("没有找到账号文件")
        return
    
    print(f"找到 {len(account_files)} 个账号文件:")
    for i, filename in enumerate(account_files):
        username = filename.replace(".json", "")
        print(f"{i+1}. {username}")
    
    file_index = input("\n输入要查看的文件序号 (直接回车退出): ")
    if file_index and file_index.isdigit() and 1 <= int(file_index) <= len(account_files):
        filename = account_files[int(file_index) - 1]
        with open(os.path.join(account_dir, filename), 'r', encoding='utf-8') as f:
            account_data = json.load(f)
            print("\n账号文件内容:")
            print(json.dumps(account_data, indent=2, ensure_ascii=False))

def main():
    """主函数"""
    print("PikPak 账号信息查看工具")
    print("==================")
    print("1. 查看数据库中的注册账号")
    print("2. 查看本地账号文件")
    print("0. 退出")
    
    choice = input("\n请选择操作: ")
    
    if choice == "1":
        view_registered_accounts()
    elif choice == "2":
        view_local_account_files()
    elif choice == "0":
        return
    else:
        print("无效的选择")

if __name__ == "__main__":
    main() 