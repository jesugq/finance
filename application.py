import os

import sqlite3
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = sqlite3.connect("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """ Deposit more cash on the account """

    rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cash = float(rows[0]["cash"])

    # User reached route via POST
    if request.method == "POST":

        # Ensure money was submitted
        if not request.form.get("money"):
            return apology("must provide amount", 403)

        # Ensure money is valid
        if float(request.form.get("money")) <= 0:
            return apology("must provide correct amount", 403)

        # Query DB for cash deposit
        money = float(request.form.get("money"))
        rows = db.execute("UPDATE users SET cash = :amount", amount=cash + money)

        return redirect("/")

    # User reached route via GET
    else:

        # Query DB for user's cash
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        cash = float(rows[0]["cash"])

        return render_template("deposit.html", cash=cash)

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Query DB for user's shares
    rows = db.execute("SELECT * FROM shares WHERE user_id = :user_id", user_id=session["user_id"])

    # Query API for each of the user's share's prices
    for row in rows:
        response = lookup(row["symbol"])
        row["price"] = response["price"]
        row["usd"] = usd(response["price"])
        row["name"] = response["name"]
        row["total"] = usd(row["shares"] * row["price"])

    # Query DB for user's cash
    user = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cash = usd(user[0]["cash"])

    return render_template("index.html", rows=rows, cash=cash)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # Ensure shares was submitted
        if not request.form.get("shares"):
            return apology("must provide shares", 403)

        # Ensure shares is positive
        if int(request.form.get("shares")) <= 0:
            return apology("must provide a valid shares", 403)

        # Query API for stock's price
        response = lookup(request.form.get("symbol"))

        # Ensure a proper symbol was inserted
        if not response:
            return apology("stock symbol doesn't exist", 403)

        # Ensure user has enough money
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        cash = float(rows[0]["cash"])
        shares = int(request.form.get("shares"))
        if response["price"] * shares > cash:
            return apology("not enough money to purchase", 403)

        # Query DB for shares purchase
        rows = db.execute("INSERT INTO history (user_id, symbol, shares, buy_price, total_price) VALUES (:user_id, :symbol, :shares, :buy_price, :total_price)", user_id=session["user_id"], symbol=response["symbol"], shares=shares, buy_price=response["price"], total_price=response["price"] * shares)
        rows = db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=(cash - response["price"] * shares), user_id=session["user_id"])
        rows = db.execute("SELECT shares FROM shares WHERE user_id = :user_id AND symbol = :symbol", user_id=session["user_id"], symbol=response["symbol"])
        if len(rows) == 0:
            db.execute("INSERT INTO shares (user_id, symbol, shares) VALUES (:user_id, :symbol, :shares)", user_id=session["user_id"], symbol=response["symbol"], shares=shares)
        else:
            db.execute("UPDATE shares SET shares = :shares WHERE user_id = :user_id AND symbol = :symbol", shares=shares + int(rows[0]["shares"]), user_id=session["user_id"], symbol=response["symbol"])

        return redirect("/")


    # User reached route via GET
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query DB for user's history
    rows = db.execute("SELECT * FROM history WHERE user_id = :user_id", user_id=session["user_id"])

    for row in rows:
        response = lookup(row["symbol"])
        row["price"] = usd(response["price"])
        row["name"] = response["name"]

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query DB for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 403)

        # Query API for stock's price
        response = lookup(request.form.get("symbol"))

        # Ensure a proper response was returned
        if not response:
            return apology("stock symbol doesn't exist", 403)

        return render_template("quoted.html", name=response["name"], price=usd(response["price"]), symbol=response["symbol"])

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure username is unique
        repeated = db.execute("SELECT id FROM users WHERE username = :username", username=request.form.get("username"))
        if len(repeated) > 0:
            return apology("username is taken", 403)

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure confirmation was submitted
        if not request.form.get("confirmation"):
            return apology("must provide confirmation", 403)

        # Ensure password and confirmation are the same
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match")

        # Query DB for user's registry
        username = request.form.get("username")
        password = request.form.get("password")
        pwhash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
        user_id = db.execute("INSERT INTO users (username, hash) VALUES (:username, :pwhash)", username=username, pwhash=pwhash)

        # Remember which user has logged in (automatically after creation)
        session["user_id"] = user_id

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)

        # Ensure shares was submitted
        if not request.form.get("shares"):
            return apology("must provide shares", 403)

        # Ensure shares is positive
        if int(request.form.get("shares")) <= 0:
            return apology("must provide a valid shares", 403)

        # Query API for stock's price
        response = lookup(request.form.get("symbol"))

        # Ensure a proper symbol was inserted
        if not response:
            return apology("stock symbol doesn't exist", 403)

        # Ensure user has enough shares
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))
        price = response["price"]
        rows = db.execute("SELECT * FROM shares WHERE user_id = :user_id AND symbol = :symbol", user_id=session["user_id"], symbol=symbol)
        if len(rows) == 0:
            return apology("shares not purchased")
        if int(rows[0]["shares"]) < shares:
            return apology("not enough shares in stock", 403)

        # Query DB for shares sell
        cash = float(db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"])
        ownd = int(db.execute("SELECT shares FROM shares WHERE user_id = :user_id AND symbol = :symbol", user_id=session["user_id"], symbol=symbol)[0]["shares"])
        rows = db.execute("INSERT INTO history (user_id, symbol, shares, buy_price, total_price) VALUES (:user_id, :symbol, :shares, :buy_price, :total_price)", user_id=session["user_id"], symbol=symbol, shares=shares * -1, buy_price=price * -1, total_price=price * shares * -1)
        rows = db.execute("UPDATE USERS set cash = :cash WHERE id = :user_id", cash=(cash + price * shares), user_id=session["user_id"])
        rows = db.execute("UPDATE shares SET shares = :shares WHERE user_id = :user_id AND symbol = :symbol", shares=ownd - shares, user_id=session["user_id"], symbol=symbol)

        return redirect("/")

    # User reached route via GET
    else:
        return render_template("sell.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
