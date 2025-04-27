#!/bin/bash

# 初始化数据库
echo "初始化数据库..."
python db_init.py

# 启动自动注册程序
echo "启动自动注册程序..."
python auto_register.py 