from flask import abort

import flask

app = flask.Flask(__name__)


class AvatarDataBase:
    def __init__(self):
        print("Initializing Avatar Data Base")
        self.avatar_map = {
            1: "./avatars/0001.jpg",
            2: "./avatars/2.jpg",
            3: "./avatars/3.webp",
        }
        self.group_avatar_map = {
            1: "./groups/0001.jpg",
        }

    def get_by_id(self, uid: int):
        if uid in self.avatar_map:
            return self.avatar_map[uid]
        else:
            return None


db = AvatarDataBase()


@app.route('/avatar/<int:uid>')
def get_avatar(uid: int):
    res = db.get_by_id(uid)
    if res:
        return flask.send_file(res)
    else:
        return abort(404)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
