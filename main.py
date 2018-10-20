from flask import Flask, request, render_template, Response, make_response, redirect

import json
from json import JSONDecoder
from collections import namedtuple
from datetime import datetime, timedelta, timezone
try:
    import config
except Exception as ex:
    import config_default as config

app = Flask(__name__)

autosave_thread = None


def init():
    app.config["songs"] = {}
    app.config["next_id"] = 1
    app.config["by_id"] = {}
    load_data()
    from threading import Thread
    autosave_thread = Thread(target=save_data)
    # autosave_thread.start()


def load_data():
    from os import path
    if path.exists("autosave.bak"):
        with open("autosave.bak", "r") as file:
            json_obj = json.load(file)
            if "next_id" not in json_obj:
                app.config["songs"] = json_obj
            else:
                app.config["songs"] = json_obj["songs"]
                app.config["next_id"] = json_obj["next_id"]
                app.config["by_id"] = json_obj["by_id"]
        print("Loaded:{}".format(json_obj))


def save_data():
    from time import sleep
    saving = {
        "next_id": app.config["next_id"],
        "songs": app.config["songs"],
        "by_id": app.config["by_id"]
    }
    print("Saving...{}".format(saving))
    with open("autosave.bak", "w") as file:
        json.dump(saving, file)


@app.context_processor
def consts():
    return {
        "SALT": config.SALT,
        "DEBUG": config.DEBUG
    }


@app.route("/favicon.ico", methods=["POST", "GET"])
def favicon():
    return redirect("/static/favicon.ico")


@app.route("/", methods=["GET"])
def main_page():
    return render_template("main.html", ORDER_LIMIT=config.MAX_ORDER_TIME_PER_DAY)


@app.route("/play_list", methods=["POST", "GET"])
def dj_panel():
    return render_template("play_list.html")


@app.route("/modify")
def modify_page():
    return render_template("modify_submit.html")


@app.route("/api/submit", methods=["POST"])
def submit():
    submit_time = int(request.cookies.get("submit_time", 0))
    if submit_time >= config.MAX_ORDER_TIME_PER_DAY:
        return encode_json({
            "status": -1,
            "message": "您的提交次数过多"
        })
    import random
    decoder = JSONDecoder()
    submit_data = decoder.decode(request.form["data"])
    song_id = str(submit_data["song"])
    if song_id not in app.config["songs"]:
        app.config["songs"][song_id] = list()
    submit_id = str(app.config["next_id"])
    app.config["next_id"] += 1
    password = str(random.randint(100000, 999999))
    order = {
        "song_id": song_id,
        "orderer": submit_data["orderer"],
        "orderto": submit_data["orderto"],
        "comment": submit_data["comment"],
        "anonymous": submit_data["anonymous"],
        "time": str((datetime.now()).astimezone(timezone(timedelta(hours=8))).strftime("%Y.%m.%d %H:%M")),
        "submit_id": submit_id,
        "password": password
    }
    app.config["songs"][song_id].append(submit_id)
    app.config["by_id"][submit_id] = order
    save_data()
    resp: Response = make_response(encode_json({
        "status": 0,
        "submit_id": submit_id,
        "password": password
    }))
    resp.set_cookie("submit_time", str(submit_time+1),
                    expires=datetime.today()+timedelta(days=1))
    return resp


@app.route("/api/order_list", methods=["POST", "GET"])
def order_list():
    result = {
    }
    for k, v in app.config["songs"].items():
        v.sort()
        if len(v) == 0:
            continue
        result[str(k)] = {
            "count": len(v),
            "min_submit_id": v[0]
        }
    return json.JSONEncoder().encode(result)


@app.route("/api/dj_list", methods=["POST", "GET"])
def dj_list():
    from copy import deepcopy
    password = request.args.get("password", "???")
    result = {

    }
    is_admin = False
    if get_md5(config.DJ_PASSWORD) == password.lower():
        for k, v in app.config["songs"].items():
            result[k] = list()
            for order in v:
                order_obj = app.config["by_id"][order]
                result[k].append(deepcopy(order_obj))
                if order_obj["anonymous"]:
                    result[k][-1]["orderer"] = "匿名"
                del result[k][-1]["anonymous"]
                del result[k][-1]["password"]
    elif get_md5(config.ADMIN_PASSWORD) == password.lower():
        result = {}
        for k, v in app.config["songs"].items():
            result[k] = list()
            for idx in v:
                result[k].append(app.config["by_id"][idx])
        is_admin = True
    else:
        return encode_json({
            "status": -1,
            "message": "密码错误."
        })
    return encode_json({
        "status": 0,
        "is_admin": is_admin,
        "data": result
    })


@app.route("/api/remove_order", methods=["POST"])
def remove_order():
    if request.form["password"] != get_md5(config.ADMIN_PASSWORD):
        return encode_json({
            "status": -1,
            "message": "密码错误."
        })
    print(request.form)
    submit_id = str(request.form["submit_id"])
    if submit_id not in app.config["by_id"]:
        return encode_json({
            "status": -1,
            "message": "未知歌曲ID"
        })
    order_obj = app.config["by_id"][submit_id]
    del app.config["by_id"][submit_id]
    app.config["songs"][order_obj["song_id"]].remove(submit_id)
    if len(app.config["songs"][order_obj["song_id"]]) == 0:
        del app.config["songs"][order_obj["song_id"]]
    save_data()
    return encode_json({
        "status": 0
    })


@app.route("/api/remove_song", methods=["POST"])
def remove_song():
    if request.form["password"] != get_md5(config.ADMIN_PASSWORD):
        return encode_json({
            "status": -1,
            "message": "密码错误."
        })
    if request.form["id"] not in app.config["songs"]:
        return encode_json({
            "status": -1,
            "message": "未知歌曲ID"
        })
    for submit_id in app.config["songs"][request.form["id"]]:
        del app.config["by_id"][submit_id]
    del app.config["songs"][request.form["id"]]
    save_data()
    return encode_json({
        "status": 0
    })


@app.route("/api/query_order", methods=["POST"])
def query_order():
    submit_id = request.form["submit_id"]
    password = request.form["password"]
    if submit_id not in app.config["by_id"]:
        return encode_json({
            "status": -1,
            "message": "提交ID不存在"
        })
    if password.lower() != get_md5(app.config["by_id"][str(submit_id)]["password"]).lower():
        return encode_json({
            "status": -1,
            "message": "密码错误"
        })
    from copy import deepcopy
    result = deepcopy(app.config["by_id"][submit_id])
    del result["password"]
    del result["submit_id"]
    return encode_json({
        "status": 0,
        "data": result
    })


@app.route("/api/modify_order", methods=["POST"])
def modify_order():
    print(request.form)
    submit_id = request.form["submit_id"]
    password = request.form["password"]
    order = JSONDecoder().decode(request.form["data"])
    if submit_id not in app.config["by_id"]:
        return encode_json({
            "status": -1,
            "message": "未知提交ID"
        })
    if password.lower() != get_md5(app.config["by_id"][str(submit_id)]["password"]):
        return encode_json({
            "status": -1,
            "message": "密码错误"
        })
    pre_song_id = app.config["by_id"][submit_id]["song_id"]
    if submit_id in app.config["songs"][pre_song_id]:
        app.config["songs"][pre_song_id].remove(str(submit_id))
    for key in order:
        app.config["by_id"][submit_id][key] = order[key]
    song_id = order["song_id"]
    if song_id not in app.config["songs"]:
        app.config["songs"][song_id] = list()
    app.config["songs"][song_id].append(submit_id)
    save_data()
    return encode_json({
        "status": 0
    })


def encode_json(text):
    return json.JSONEncoder().encode(text)


def get_md5(text: str):
    import hashlib
    return str(hashlib.md5((config.SALT+str(text)).encode("utf-8")).hexdigest()).lower()


if __name__ == "__main__":
    init()
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
