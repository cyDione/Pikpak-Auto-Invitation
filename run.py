import json
import os
import time
import uuid
import webbrowser

import requests
from flask import Flask, render_template, request, jsonify, session

# 导入 pikpak.py 中的函数
from utils.pk_email import connect_imap
from utils.pikpak import (
    sign_encrypt,
    captcha_image_parse,
    ramdom_version,
    random_rtc_token,
    PikPak,
    save_account_info,
    test_proxy,
)

app = Flask(__name__)
app.secret_key = os.urandom(24)


@app.route("/")
def index():
    return render_template("index.html")

@app.route('/health')
def health_check():
    return jsonify({"status": "OK"})
    
@app.route("/initialize", methods=["POST"])
def initialize():
    # 获取用户表单输入
    use_proxy = request.form.get("use_proxy") == "true"
    proxy_url = request.form.get("proxy_url", "http://127.0.0.1:7890")
    invite_code = request.form.get("invite_code", "")
    email = request.form.get("email", "")

    # 初始化参数
    current_version = ramdom_version()
    version = current_version["v"]
    algorithms = current_version["algorithms"]
    client_id = "YNxT9w7GMdWvEOKa"
    client_secret = "dbw2OtmVEeuUvIptb1Coyg"
    package_name = "com.pikcloud.pikpak"
    device_id = str(uuid.uuid4()).replace("-", "")
    rtc_token = random_rtc_token()

    # 将这些参数存储到会话中以便后续使用
    session["use_proxy"] = use_proxy
    session["proxy_url"] = proxy_url
    session["invite_code"] = invite_code
    session["email"] = email
    session["version"] = version
    session["algorithms"] = algorithms
    session["client_id"] = client_id
    session["client_secret"] = client_secret
    session["package_name"] = package_name
    session["device_id"] = device_id
    session["rtc_token"] = rtc_token

    # 如果启用代理，则测试代理
    proxy_status = None
    if use_proxy:
        proxy_status = test_proxy(proxy_url)

    # 创建PikPak实例
    pikpak = PikPak(
        invite_code,
        client_id,
        device_id,
        version,
        algorithms,
        email,
        rtc_token,
        client_secret,
        package_name,
        use_proxy=use_proxy,
        proxy_http=proxy_url,
        proxy_https=proxy_url,
    )

    # 初始化验证码
    init_result = pikpak.init("POST:/v1/auth/verification")
    if (
        not init_result
        or not isinstance(init_result, dict)
        or "captcha_token" not in init_result
    ):
        return jsonify(
            {"status": "error", "message": "初始化失败，请检查网络连接或代理设置"}
        )

    # 将验证码令牌保存到会话中
    session["captcha_token"] = pikpak.captcha_token

    return jsonify(
        {
            "status": "success",
            "message": "初始化成功，请进行滑块验证",
            "proxy_status": proxy_status,
            "version": version,
            "device_id": device_id,
            "rtc_token": rtc_token,
        }
    )


@app.route("/verify_captcha", methods=["POST"])
def verify_captcha():
    # 从会话中获取存储的数据
    device_id = session.get("device_id")
    email = session.get("email")
    invite_code = session.get("invite_code")
    client_id = session.get("client_id")
    version = session.get("version")
    algorithms = session.get("algorithms")
    rtc_token = session.get("rtc_token")
    client_secret = session.get("client_secret")
    package_name = session.get("package_name")
    use_proxy = session.get("use_proxy")
    proxy_url = session.get("proxy_url")

    if not device_id or not email:
        return jsonify({"status": "error", "message": "会话已过期，请重新初始化"})

    # 创建PikPak实例
    pikpak = PikPak(
        invite_code,
        client_id,
        device_id,
        version,
        algorithms,
        email,
        rtc_token,
        client_secret,
        package_name,
        use_proxy=use_proxy,
        proxy_http=proxy_url,
        proxy_https=proxy_url,
    )

    # 从会话中设置验证码令牌
    pikpak.captcha_token = session.get("captcha_token", "")

    # 尝试验证码验证
    max_attempts = 5
    captcha_result = None

    for attempt in range(max_attempts):
        try:
            captcha_result = captcha_image_parse(pikpak, device_id)
            if (
                captcha_result
                and "response_data" in captcha_result
                and captcha_result["response_data"].get("result") == "accept"
            ):
                break
            time.sleep(2)
        except Exception as e:
            time.sleep(2)

    if (
        not captcha_result
        or "response_data" not in captcha_result
        or captcha_result["response_data"].get("result") != "accept"
    ):
        return jsonify({"status": "error", "message": "滑块验证失败，请重试"})

    # 滑块验证加密
    try:
        executor_info = pikpak.executor()
        if not executor_info:
            return jsonify({"status": "error", "message": "获取executor信息失败"})

        sign_encrypt_info = sign_encrypt(
            executor_info,
            pikpak.captcha_token,
            rtc_token,
            pikpak.use_proxy,
            pikpak.proxies,
        )
        if (
            not sign_encrypt_info
            or "request_id" not in sign_encrypt_info
            or "sign" not in sign_encrypt_info
        ):
            return jsonify({"status": "error", "message": "签名加密失败"})

        # 更新验证码令牌
        report_result = pikpak.report(
            sign_encrypt_info["request_id"],
            sign_encrypt_info["sign"],
            captcha_result["pid"],
            captcha_result["traceid"],
        )

        # 请求邮箱验证码
        verification_result = pikpak.verification()
        if (
            not verification_result
            or not isinstance(verification_result, dict)
            or "verification_id" not in verification_result
        ):
            return jsonify({"status": "error", "message": "请求验证码失败"})

        # 将更新的数据保存到会话中
        session["captcha_token"] = pikpak.captcha_token
        session["verification_id"] = pikpak.verification_id

        return jsonify({"status": "success", "message": "验证码已发送到邮箱，请查收"})

    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        return jsonify(
            {
                "status": "error",
                "message": f"验证过程出错: {str(e)}",
                "trace": error_trace,
            }
        )


@app.route("/register", methods=["POST"])
def register():
    # 从表单获取验证码
    verification_code = request.form.get("verification_code")

    if not verification_code:
        return jsonify({"status": "error", "message": "验证码不能为空"})

    # 从会话中获取存储的数据
    device_id = session.get("device_id")
    email = session.get("email")
    invite_code = session.get("invite_code")
    client_id = session.get("client_id")
    version = session.get("version")
    algorithms = session.get("algorithms")
    rtc_token = session.get("rtc_token")
    client_secret = session.get("client_secret")
    package_name = session.get("package_name")
    use_proxy = session.get("use_proxy")
    proxy_url = session.get("proxy_url")
    verification_id = session.get("verification_id")

    if not device_id or not email or not verification_id:
        return jsonify({"status": "error", "message": "会话已过期，请重新初始化"})

    # 创建PikPak实例
    pikpak = PikPak(
        invite_code,
        client_id,
        device_id,
        version,
        algorithms,
        email,
        rtc_token,
        client_secret,
        package_name,
        use_proxy=use_proxy,
        proxy_http=proxy_url,
        proxy_https=proxy_url,
    )

    # 从会话中设置验证码令牌和验证ID
    pikpak.captcha_token = session.get("captcha_token", "")
    pikpak.verification_id = verification_id

    # 验证验证码
    pikpak.verify_post(verification_code)

    # 刷新时间戳并加密签名值
    pikpak.init("POST:/v1/auth/signup")

    # 注册并登录
    name = email.split("@")[0]
    password = "zhiyuan233"  # 默认密码
    signup_result = pikpak.signup(name, password, verification_code)

    # 填写邀请码
    pikpak.activation_code()

    if (
        not signup_result
        or not isinstance(signup_result, dict)
        or "access_token" not in signup_result
    ):
        return jsonify({"status": "error", "message": "注册失败，请检查验证码或重试"})

    # 保存账号信息到JSON文件
    account_info = {
        "captcha_token": pikpak.captcha_token,
        "timestamp": pikpak.timestamp,
        "name": name,
        "email": email,
        "password": password,
        "device_id": device_id,
        "version": version,
        "user_id": signup_result.get("sub", ""),
        "access_token": signup_result.get("access_token", ""),
        "refresh_token": signup_result.get("refresh_token", ""),
    }

    # 保存账号信息
    account_file = save_account_info(name, account_info)

    return jsonify(
        {
            "status": "success",
            "message": "注册成功！账号已保存。",
            "account_info": account_info,
        }
    )


@app.route("/test_proxy", methods=["POST"])
def test_proxy_route():
    proxy_url = request.form.get("proxy_url", "http://127.0.0.1:7890")
    result = test_proxy(proxy_url)

    return jsonify(
        {
            "status": "success" if result else "error",
            "message": "代理连接测试成功" if result else "代理连接测试失败",
        }
    )


@app.route("/get_verification", methods=["POST"])
def get_verification():
    """
    处理获取验证码的请求
    """
    email_user = request.form["email"]
    email_password = request.form["password"]

    # 先尝试从收件箱获取验证码
    result = connect_imap(email_user, email_password, "INBOX")

    # 如果收件箱没有找到验证码，则尝试从垃圾邮件中查找
    if result["code"] == 0:
        result = connect_imap(email_user, email_password, "Junk")

    return jsonify(result)


@app.route("/fetch_accounts", methods=["GET"])
def fetch_accounts():
    # 获取account文件夹中的所有JSON文件
    account_files = []
    for file in os.listdir("account"):
        if file.endswith(".json"):
            file_path = os.path.join("account", file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    account_data = json.load(f)
                    if isinstance(account_data, dict):
                        # 添加文件名属性，用于后续操作
                        account_data["filename"] = file
                        account_files.append(account_data)
            except Exception as e:
                print(f"Error reading {file}: {str(e)}")

    if not account_files:
        return jsonify(
            {"status": "info", "message": "没有找到保存的账号", "accounts": []}
        )

    # 按文件名排序（通常包含日期时间）
    account_files.sort(key=lambda x: x.get("filename", ""), reverse=True)

    return jsonify(
        {
            "status": "success",
            "message": f"找到 {len(account_files)} 个账号",
            "accounts": account_files,
        }
    )


@app.route("/update_account", methods=["POST"])
def update_account():
    data = request.json
    if not data or "filename" not in data or "account_data" not in data:
        return jsonify({"status": "error", "message": "请求数据不完整"})

    filename = data.get("filename")
    account_data = data.get("account_data")

    # 安全检查文件名
    if not filename or ".." in filename or not filename.endswith(".json"):
        return jsonify({"status": "error", "message": "无效的文件名"})

    file_path = os.path.join("account", filename)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(account_data, f, indent=4, ensure_ascii=False)

        return jsonify({"status": "success", "message": "账号已成功更新"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"更新账号时出错: {str(e)}"})


@app.route("/delete_account", methods=["POST"])
def delete_account():
    filename = request.form.get("filename")

    if not filename:
        return jsonify({"status": "error", "message": "未提供文件名"})

    # 安全检查文件名
    if ".." in filename or not filename.endswith(".json"):
        return jsonify({"status": "error", "message": "无效的文件名"})

    file_path = os.path.join("account", filename)

    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": "账号文件不存在"})

        # 删除文件
        os.remove(file_path)

        return jsonify({"status": "success", "message": "账号已成功删除"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"删除账号时出错: {str(e)}"})


@app.route("/activate_account", methods=["POST"])
def activate_account():
    try:
        data = request.json
        account_data = data.get("info")
        key = data.get("key")

        if not account_data or not key:
            return jsonify({"status": "error", "message": "账号数据或密钥不能为空"})

        # 发送请求到外部API
        response = requests.post(
            headers={
                "Content-Type": "application/json",
                "referer": "https://inject.kiteyuan.info/",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
            },
            url="https://inject.kiteyuan.info/infoInject",
            json={"info": account_data, "key": key},
            timeout=30,
        )

        if response.status_code == 200:
            return jsonify(
                {
                    "status": "success",
                    "message": "账号激活成功",
                    "result": response.json(),
                }
            )
        else:
            return jsonify(
                {
                    "status": "error",
                    "message": f"激活失败: HTTP {response.status_code}",
                    "result": response.text,
                }
            )

    except Exception as e:
        return jsonify({"status": "error", "message": f"操作失败: {str(e)}"})


@app.route("/check_email_inventory", methods=["GET"])
def check_email_inventory():
    try:
        # 发送请求到库存API
        response = requests.get(
            url="https://zizhu.shanyouxiang.com/kucun",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            },
            timeout=10,
        )

        if response.status_code == 200:
            return jsonify({"status": "success", "inventory": response.json()})
        else:
            return jsonify(
                {
                    "status": "error",
                    "message": f"获取库存失败: HTTP {response.status_code}",
                }
            )

    except Exception as e:
        return jsonify({"status": "error", "message": f"获取库存时出错: {str(e)}"})


@app.route("/check_balance", methods=["GET"])
def check_balance():
    try:
        # 从请求参数中获取卡号
        card = request.args.get("card")

        if not card:
            return jsonify({"status": "error", "message": "未提供卡号参数"})

        # 发送请求到余额查询API
        response = requests.get(
            url="https://zizhu.shanyouxiang.com/yue",
            params={"card": card},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            },
            timeout=10,
        )

        if response.status_code == 200:
            return jsonify({"status": "success", "balance": response.json()})
        else:
            return jsonify(
                {
                    "status": "error",
                    "message": f"查询余额失败: HTTP {response.status_code}",
                }
            )

    except Exception as e:
        return jsonify({"status": "error", "message": f"查询余额时出错: {str(e)}"})


@app.route("/extract_emails", methods=["GET"])
def extract_emails():
    try:
        # 从请求参数中获取必需的参数
        card = request.args.get("card")
        shuliang = request.args.get("shuliang")
        leixing = request.args.get("leixing")
        # 获取前端传递的重试次数计数器，如果没有则初始化为0
        frontend_retry_count = int(request.args.get("retry_count", "0"))

        # 验证必需的参数
        if not card:
            return jsonify({"status": "error", "message": "未提供卡号参数"})

        if not shuliang:
            return jsonify({"status": "error", "message": "未提供提取数量参数"})

        if not leixing or leixing not in ["outlook", "hotmail"]:
            return jsonify(
                {
                    "status": "error",
                    "message": "提取类型参数无效，必须为 outlook 或 hotmail",
                }
            )

        # 尝试将数量转换为整数
        try:
            shuliang_int = int(shuliang)
            if shuliang_int < 1 or shuliang_int > 2000:
                return jsonify(
                    {"status": "error", "message": "提取数量必须在1到2000之间"}
                )
        except ValueError:
            return jsonify({"status": "error", "message": "提取数量必须为整数"})

        # 后端重试计数器
        retry_count = 0
        max_retries = 20  # 单次后端请求的最大重试次数
        retry_delay = 0   # 每次重试间隔秒数
        
        # 记录总的前端+后端重试次数，用于展示给用户
        total_retry_count = frontend_retry_count
        
        while retry_count < max_retries:
            # 发送请求到邮箱提取API
            response = requests.get(
                url="https://zizhu.shanyouxiang.com/huoqu",
                params={"card": card, "shuliang": shuliang, "leixing": leixing},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                },
                timeout=10,  # 降低单次请求的超时时间，以便更快地进行重试
            )

            if response.status_code == 200:
                # 检查响应是否为JSON格式，如果是，通常表示没有库存
                try:
                    json_response = response.json()
                    if isinstance(json_response, dict) and "msg" in json_response:
                        # 没有库存，需要重试
                        retry_count += 1
                        total_retry_count += 1
                        
                        # 如果达到后端最大重试次数，返回特殊状态让前端继续重试
                        if retry_count >= max_retries:
                            return jsonify({
                                "status": "retry", 
                                "message": f"暂无库存: {json_response['msg']}，已重试{total_retry_count}次，继续尝试中...",
                                "retry_count": total_retry_count
                            })
                        
                        # 等待一段时间后重试
                        time.sleep(retry_delay)
                        continue
                except ValueError:
                    # 不是JSON格式，可能是成功的文本列表响应
                    pass
                
                # 处理文本响应
                response_text = response.text.strip()

                # 解析响应文本为邮箱列表
                emails = []
                if response_text:
                    for line in response_text.split("\n"):
                        if line.strip():
                            emails.append(line.strip())

                # 如果没有实际提取到邮箱（可能是空文本响应），继续重试
                if not emails:
                    retry_count += 1
                    total_retry_count += 1
                    
                    if retry_count >= max_retries:
                        return jsonify({
                            "status": "retry", 
                            "message": f"未能获取到邮箱，已重试{total_retry_count}次，继续尝试中...",
                            "retry_count": total_retry_count
                        })
                    
                    time.sleep(retry_delay)
                    continue

                # 成功获取到邮箱，返回结果
                return jsonify(
                    {
                        "status": "success", 
                        "emails": emails, 
                        "count": len(emails), 
                        "retries": total_retry_count,
                        "message": f"成功获取{len(emails)}个邮箱，总共重试{total_retry_count}次"
                    }
                )
            else:
                # 请求失败，返回错误
                return jsonify(
                    {
                        "status": "error",
                        "message": f"提取邮箱失败: HTTP {response.status_code}",
                        "response": response.text,
                    }
                )

        # 如果执行到这里，说明超过了最大重试次数
        return jsonify({
            "status": "retry",
            "message": f"暂无邮箱库存，已重试{total_retry_count}次，继续尝试中...",
            "retry_count": total_retry_count
        })

    except Exception as e:
        return jsonify({"status": "error", "message": f"提取邮箱时出错: {str(e)}"})


if __name__ == "__main__":
    webbrowser.open('http://localhost:2314/')
    app.run(debug=False, host="0.0.0.0", port=2314)
