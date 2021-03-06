# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/

import datetime
import os
import os.path
import urlparse

from flask import request, session, render_template, redirect, url_for, jsonify, Response
from pymongo import MongoClient, DESCENDING
from bson.objectid import ObjectId

from boogs import BugBuilder

import requests

from stooge.frontend.persona import verify_assertion
from stooge.frontend import app
from stooge.frontend.mozillians import lookup_mozillian

client = MongoClient()
users = client.stooge.users
scans = client.stooge.scans
sites = client.stooge.sites


# This is horrible. Just to be able to set a Cache-Control header on
# static content. Look for something better.

def root_dir():
    return os.path.abspath(os.path.dirname(__file__))

def get_static_file(filename):  # pragma: no cover
    src = os.path.join(root_dir(), 'static', filename)
    with open(src) as f:
        return f.read()


@app.route("/")
def index():
    if session.get('email') is None:
        return redirect(url_for('login'))
    content = get_static_file('index.html')
    return Response(content, mimetype="text/html", headers={"Cache-Control":"private"})
    #return app.send_static_file('index.html')

@app.route("/login")
def login():
    if session.get('email') is not None:
        return redirect(url_for('index'))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/persona/login", methods=["POST"])
def persona_login():
    receipt = verify_assertion(request.form['assertion'], request.host)
    if not receipt:
        return jsonify(success=False)
    if not receipt['email'].endswith('@mozilla.com') and not receipt['email'].endswith('@mozillafoundation.org'):
        mozillian = lookup_mozillian(app.config["MOZILLIANS_APP_NAME"], app.config["MOZILLIANS_APP_KEY"], receipt['email'])
        if not mozillian or not mozillian['is_vouched']:
            return jsonify(success=False, error="only-mozilla")
    session['email'] = receipt['email']
    users.update({"email":receipt["email"]}, {"email":receipt["email"], "last_login": datetime.datetime.utcnow()}, upsert=True)
    return jsonify(success=True, email=receipt['email'])

@app.route('/api/session')
def api_session():
    if session.get('email') is None:
        return jsonify(success=False)
    return jsonify(success=True, data={'email': session['email']})

@app.route('/api/scan/<scan_id>')
def api_scan(scan_id):
    if session.get('email') is None:
        return jsonify(success=False)

    if scan_id == 'last':
        query = {"tags":"nightly"}
        if not app.config.get("DEBUG"):
            query["state"] = "FINISHED" # In debug mode we also show scans in progress
        scan = scans.find_one(query, {"sites.responses": 0}, sort=[("created", DESCENDING)])
    else:
        scan = scans.find_one({"_id": ObjectId(scan_id)}, {"sites.responses": 0})

    # Merge in the owner and type so that we dont have to run a new scan to get those
    for scan_site in scan["sites"]:
        site = sites.find_one({"_id": ObjectId(scan_site["_id"])})
        if site:
            scan_site["owner"] = site["owner"]
            scan_site["type"] = site["type"]

    return jsonify(success=True, data=scan)
