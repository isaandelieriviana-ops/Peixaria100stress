
import os, sqlite3, json
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(APP_DIR, "100stress.db"))
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-antes-de-publicar-100stress")

def db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT);
        CREATE TABLE IF NOT EXISTS products (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT DEFAULT 'Peixes',
          description TEXT DEFAULT '', price REAL NOT NULL DEFAULT 0, unit TEXT DEFAULT 'kg',
          stock REAL NOT NULL DEFAULT 0, active INTEGER DEFAULT 1, promo_price REAL,
          water TEXT DEFAULT 'Tanto faz', flavor TEXT DEFAULT 'Intermediário',
          texture TEXT DEFAULT 'Firme', bones TEXT DEFAULT 'Possui espinhas',
          origin TEXT DEFAULT '', preparation TEXT DEFAULT '', image TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT, customer TEXT, phone TEXT, address TEXT,
          items TEXT, subtotal REAL, delivery REAL, total REAL, payment TEXT,
          status TEXT DEFAULT 'Recebido', channel TEXT DEFAULT 'Online',
          created_at TEXT, notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS expenses (
          id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT, category TEXT,
          amount REAL, date TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        """)
        if not con.execute("SELECT id FROM users WHERE username='admin'").fetchone():
            con.execute("INSERT INTO users(username,password) VALUES(?,?)",
                        ("admin", generate_password_hash("admin123")))
        if not con.execute("SELECT id FROM products LIMIT 1").fetchone():
            sample = [
              ("Tilápia","Peixes","Sabor suave e carne branca. Boa para grelha, forno e frigideira.",29.90,"kg",22,"Água doce","Suave","Firme","Pode ter espinhas","Brasil","Grelha, forno ou fritura",""),
              ("Salmão","Peixes","Peixe de sabor característico e carne macia. Consulte a apresentação disponível.",79.90,"kg",8,"Água salgada","Marcante","Macia","Verificar apresentação","Consultar fornecedor","Forno, grelha ou frigideira",""),
              ("Merluza","Peixes","Carne clara e delicada, versátil para diferentes preparos.",39.90,"kg",14,"Água salgada","Suave","Macia","Verificar apresentação","Consultar fornecedor","Forno ou frigideira",""),
              ("Camarão","Frutos do mar","Versátil para massas, risotos e outros preparos.",59.90,"kg",10,"Água salgada","Marcante","Firme","Sem espinhas","Consultar fornecedor","Refogado, grelha ou molho",""),
              ("Lula","Frutos do mar","Pode ser preparada grelhada, empanada ou em molhos.",49.90,"kg",7,"Água salgada","Intermediário","Firme","Sem espinhas","Consultar fornecedor","Grelha, fritura ou molho",""),
              ("Polvo","Frutos do mar","Fruto do mar de textura característica; exige preparo adequado.",89.90,"kg",3,"Água salgada","Marcante","Firme","Sem espinhas","Consultar fornecedor","Cozimento e finalização na grelha",""),
              ("Tainha","Peixes","Peixe de sabor característico. Consulte disponibilidade e apresentação.",34.90,"kg",9,"Água salgada","Marcante","Firme","Possui espinhas","Consultar fornecedor","Assada ou grelhada",""),
              ("Mexilhão","Frutos do mar","Ideal para caldos, molhos e preparos com frutos do mar.",44.90,"kg",5,"Água salgada","Marcante","Macia","Sem espinhas","Consultar fornecedor","Caldeiradas e molhos",""),
            ]
            con.executemany("""INSERT INTO products(name,category,description,price,unit,stock,water,flavor,texture,bones,origin,preparation,image)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", sample)
        defaults = {
          "store_name":"Peixaria 100 Stress", "phone":"(51) 99707-8134",
          "whatsapp":"5551997078134", "address":"Região central — endereço a confirmar",
          "hours":"Consulte nossos horários pelo WhatsApp", "delivery_area":"Região central",
          "free_delivery_min":"100", "central_delivery_fee":"8", "other_delivery_fee":"12",
          "pix_key":"Cadastre aqui a chave Pix da peixaria", "notice":"Encomende com praticidade e sem estresse!"
        }
        for k,v in defaults.items():
            con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))

def get_settings():
    with db() as con:
        return {r["key"]:r["value"] for r in con.execute("SELECT * FROM settings")}

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_globals():
    return {"settings":get_settings(), "is_admin":bool(session.get("admin"))}

@app.route("/health")
def health():
    return {"status":"ok"}, 200

@app.route("/")
def home():
    with db() as con:
        products = con.execute("SELECT * FROM products WHERE active=1 ORDER BY category,name").fetchall()
    return render_template("home.html", products=products)

@app.route("/quiz")
def quiz():
    with db() as con:
        products = con.execute("SELECT * FROM products WHERE active=1 ORDER BY name").fetchall()
    return render_template("quiz.html", products=products)

@app.route("/pedido", methods=["POST"])
def place_order():
    data = request.get_json(silent=True) or request.form
    try:
        items = json.loads(data.get("items","[]")) if isinstance(data.get("items"),str) else data.get("items",[])
        if not items: return jsonify(ok=False,error="Seu carrinho está vazio."),400
        with db() as con:
            safe_items=[]; subtotal=0
            for item in items:
                p=con.execute("SELECT * FROM products WHERE id=? AND active=1",(int(item["id"]),)).fetchone()
                qty=float(item["qty"])
                if not p or qty<=0: continue
                price=float(p["promo_price"] if p["promo_price"] else p["price"])
                line=round(price*qty,2); subtotal+=line
                safe_items.append({"id":p["id"],"name":p["name"],"qty":qty,"unit":p["unit"],"price":price,"total":line})
            if not safe_items: return jsonify(ok=False,error="Não foi possível validar os produtos."),400
            s=get_settings()
            address=data.get("address","")
            zone=data.get("delivery_zone","central")
            fee=0 if data.get("pickup")=="true" else float(s.get("other_delivery_fee","12") if zone=="other" else s.get("central_delivery_fee","8"))
            if subtotal>=float(s.get("free_delivery_min","100")): fee=0
            total=round(subtotal+fee,2)
            cur=con.execute("""INSERT INTO orders(customer,phone,address,items,subtotal,delivery,total,payment,status,channel,created_at,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data.get("customer",""),data.get("phone",""),"Retirada na loja" if data.get("pickup")=="true" else address,
             json.dumps(safe_items,ensure_ascii=False),subtotal,fee,total,data.get("payment","A combinar"),
             "Aguardando confirmação","Online",datetime.now().strftime("%d/%m/%Y %H:%M"),data.get("notes","")))
            order_id=cur.lastrowid
        return jsonify(ok=True,order_id=order_id,total=total,message="Pedido recebido! A peixaria confirmará disponibilidade e pagamento pelo contato informado.")
    except Exception as e:
        return jsonify(ok=False,error="Não foi possível registrar o pedido. Confira os dados e tente novamente."),400

@app.route("/admin/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        with db() as con:
            user=con.execute("SELECT * FROM users WHERE username=?",(request.form.get("username"),)).fetchone()
        if user and check_password_hash(user["password"],request.form.get("password","")):
            session["admin"]=True
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Usuário ou senha incorretos.")
    return render_template("login.html")

@app.route("/admin/sair")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/admin")
@admin_required
def dashboard():
    with db() as con:
        products=con.execute("SELECT * FROM products ORDER BY name").fetchall()
        orders=con.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 12").fetchall()
        revenue=con.execute("SELECT COALESCE(SUM(total),0) v FROM orders WHERE status NOT IN ('Cancelado')").fetchone()["v"]
        expenses=con.execute("SELECT COALESCE(SUM(amount),0) v FROM expenses").fetchone()["v"]
        best=con.execute("""SELECT json_each.value AS name, SUM(CAST(json_extract(json_each.value,'$.qty') AS REAL)) qty
          FROM orders, json_each(orders.items) WHERE orders.status!='Cancelado' GROUP BY name ORDER BY qty DESC LIMIT 5""").fetchall()
    return render_template("admin.html",products=products,orders=orders,revenue=revenue,expenses=expenses,best=best)

@app.route("/admin/produto/novo", methods=["GET","POST"])
@app.route("/admin/produto/<int:pid>", methods=["GET","POST"])
@admin_required
def product_edit(pid=None):
    with db() as con:
        p=con.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone() if pid else None
        if request.method=="POST":
            f=request.form
            vals=(f["name"],f["category"],f.get("description",""),float(f["price"]),f.get("unit","kg"),
                  float(f.get("stock",0)),1 if f.get("active") else 0,
                  float(f["promo_price"]) if f.get("promo_price") else None,
                  f.get("water","Tanto faz"),f.get("flavor","Intermediário"),f.get("texture","Firme"),
                  f.get("bones","Possui espinhas"),f.get("origin",""),f.get("preparation",""),f.get("image",""))
            if pid:
                con.execute("""UPDATE products SET name=?,category=?,description=?,price=?,unit=?,stock=?,active=?,promo_price=?,water=?,flavor=?,texture=?,bones=?,origin=?,preparation=?,image=? WHERE id=?""",vals+(pid,))
            else:
                con.execute("""INSERT INTO products(name,category,description,price,unit,stock,active,promo_price,water,flavor,texture,bones,origin,preparation,image) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",vals)
            flash("Produto salvo com sucesso.")
            return redirect(url_for("dashboard"))
    return render_template("product_form.html",p=p)

@app.route("/admin/produto/<int:pid>/excluir",methods=["POST"])
@admin_required
def product_delete(pid):
    with db() as con: con.execute("DELETE FROM products WHERE id=?",(pid,))
    flash("Produto excluído.")
    return redirect(url_for("dashboard"))

@app.route("/admin/configuracoes",methods=["GET","POST"])
@admin_required
def settings_page():
    if request.method=="POST":
        with db() as con:
            for k,v in request.form.items():
                con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,v))
        flash("Informações da loja atualizadas.")
        return redirect(url_for("settings_page"))
    return render_template("settings.html",s=get_settings())

@app.route("/admin/pedido/<int:oid>",methods=["POST"])
@admin_required
def update_order(oid):
    with db() as con:
        con.execute("UPDATE orders SET status=? WHERE id=?",(request.form.get("status"),oid))
    flash("Situação do pedido atualizada.")
    return redirect(url_for("dashboard"))

@app.route("/admin/venda",methods=["POST"])
@admin_required
def sale():
    try:
        name=request.form["name"]; qty=float(request.form["qty"]); price=float(request.form["price"])
        with db() as con:
            p=con.execute("SELECT * FROM products WHERE id=?",(int(name),)).fetchone()
            if p:
                items=[{"id":p["id"],"name":p["name"],"qty":qty,"unit":p["unit"],"price":price,"total":qty*price}]
                con.execute("""INSERT INTO orders(customer,phone,address,items,subtotal,delivery,total,payment,status,channel,created_at,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",("Venda balcão","","Loja",json.dumps(items,ensure_ascii=False),qty*price,0,qty*price,request.form.get("payment","Dinheiro"),"Concluído","Presencial",datetime.now().strftime("%d/%m/%Y %H:%M"),""))
                con.execute("UPDATE products SET stock=MAX(0,stock-?) WHERE id=?",(qty,p["id"]))
        flash("Venda presencial registrada.")
    except Exception:
        flash("Não foi possível registrar a venda. Confira os campos.")
    return redirect(url_for("dashboard"))

@app.route("/admin/despesa",methods=["POST"])
@admin_required
def expense():
    with db() as con:
        con.execute("INSERT INTO expenses(description,category,amount,date) VALUES(?,?,?,?)",
        (request.form["description"],request.form["category"],float(request.form["amount"]),request.form.get("date",datetime.now().strftime("%Y-%m-%d"))))
    flash("Despesa registrada.")
    return redirect(url_for("dashboard"))

@app.route("/admin/estoque/<int:pid>",methods=["POST"])
@admin_required
def stock_update(pid):
    with db() as con:
        con.execute("UPDATE products SET stock=MAX(0,stock+?) WHERE id=?",(float(request.form["change"]),pid))
    flash("Estoque atualizado.")
    return redirect(url_for("dashboard"))

@app.route("/admin/alterar-senha",methods=["POST"])
@admin_required
def change_password():
    old=request.form.get("old",""); new=request.form.get("new","")
    with db() as con:
        u=con.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        if u and check_password_hash(u["password"],old) and len(new)>=8:
            con.execute("UPDATE users SET password=? WHERE username='admin'",(generate_password_hash(new),))
            flash("Senha alterada.")
        else: flash("Senha atual incorreta ou nova senha com menos de 8 caracteres.")
    return redirect(url_for("settings_page"))

init_db()  # Também executa quando o Gunicorn importa o módulo no Render.

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
