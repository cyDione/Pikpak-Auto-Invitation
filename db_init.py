import json
import psycopg2
from psycopg2 import sql

def load_config():
    """加载配置文件"""
    with open('config.json', 'r') as f:
        return json.load(f)

def init_database():
    """初始化数据库表结构"""
    config = load_config()
    conn_string = config['database']['connection_string']
    
    # 连接数据库
    conn = psycopg2.connect(conn_string)
    cursor = conn.cursor()
    
    try:
        # 创建邮箱表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            is_registered BOOLEAN DEFAULT FALSE,
            register_time TIMESTAMP,
            account_info JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # 创建注册记录表，确保可以存储完整账号信息
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id SERIAL PRIMARY KEY,
            email_id INTEGER REFERENCES emails(id),
            invite_code VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL,
            pikpak_username VARCHAR(255),
            pikpak_password VARCHAR(255),
            device_id VARCHAR(255),
            user_id VARCHAR(255),
            access_token TEXT,
            refresh_token TEXT,
            register_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            account_data JSONB,
            activation_result JSONB
        );
        """)
        
        # 检查是否需要添加新列
        try:
            cursor.execute("""
            ALTER TABLE registrations 
            ADD COLUMN IF NOT EXISTS access_token TEXT,
            ADD COLUMN IF NOT EXISTS refresh_token TEXT,
            ADD COLUMN IF NOT EXISTS user_id VARCHAR(255);
            """)
            conn.commit()
            print("已更新注册表结构，添加了token和user_id字段")
        except Exception as e:
            conn.rollback()
            print(f"更新表结构失败: {e}")
        
        conn.commit()
        print("数据库初始化成功")
    except Exception as e:
        conn.rollback()
        print(f"数据库初始化失败: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    init_database() 