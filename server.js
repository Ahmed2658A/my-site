const express=require("express");
const cors=require("cors");
const bcrypt=require("bcryptjs");
const jwt=require("jsonwebtoken");
const Database=require("better-sqlite3");
const path=require("path");
require("dotenv").config();
const app=express(); app.use(cors()); app.use(express.json());
const db=new Database(process.env.DB_FILE||"elcaysar.db");
db.exec(`
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'customer',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,category TEXT NOT NULL,price REAL NOT NULL,stock INTEGER NOT NULL DEFAULT 0,image_url TEXT,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS coupons(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,discount_type TEXT NOT NULL,discount_value REAL NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,customer_name TEXT NOT NULL,phone TEXT NOT NULL,total REAL NOT NULL,status TEXT NOT NULL DEFAULT 'pending',payment_status TEXT NOT NULL DEFAULT 'unpaid',player_uid TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER,product_id INTEGER,name TEXT NOT NULL,qty INTEGER NOT NULL,unit_price REAL NOT NULL);
`);
function auth(req,res,next){try{const h=req.headers.authorization||"";if(!h.startsWith("Bearer "))throw Error();req.user=jwt.verify(h.slice(7),process.env.JWT_SECRET);next()}catch(e){res.status(401).json({error:"unauthorized"})}}
function admin(req,res,next){if(req.user?.role!=="admin")return res.status(403).json({error:"admin_only"});next()}
app.get("/api/health",(req,res)=>res.json({ok:true,service:"ELCAYSAR STORE"}));
app.post("/api/auth/register",async(req,res)=>{const {name,email,password}=req.body||{};if(!name||!email||!password)return res.status(400).json({error:"missing_fields"});try{const hash=await bcrypt.hash(password,12);const x=db.prepare("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)").run(name,email,hash);const u={id:x.lastInsertRowid,name,email,role:"customer"};res.json({token:jwt.sign(u,process.env.JWT_SECRET),user:u})}catch(e){res.status(409).json({error:"email_exists"})}});
app.post("/api/auth/login",async(req,res)=>{const {email,password}=req.body||{};const u=db.prepare("SELECT * FROM users WHERE email=?").get(email);if(!u||!(await bcrypt.compare(password,u.password_hash)))return res.status(401).json({error:"invalid_login"});const user={id:u.id,name:u.name,email:u.email,role:u.role};res.json({token:jwt.sign(user,process.env.JWT_SECRET),user})});
app.get("/api/products",(req,res)=>res.json(db.prepare("SELECT * FROM products WHERE active=1 ORDER BY id DESC").all()));
app.post("/api/products",auth,admin,(req,res)=>{const {name,category,price,stock=0,image_url=""}=req.body;const x=db.prepare("INSERT INTO products(name,category,price,stock,image_url) VALUES(?,?,?,?,?)").run(name,category,price,stock,image_url);res.json({id:x.lastInsertRowid})});
app.patch("/api/products/:id",auth,admin,(req,res)=>{const {name,category,price,stock,image_url,active}=req.body;db.prepare("UPDATE products SET name=COALESCE(?,name),category=COALESCE(?,category),price=COALESCE(?,price),stock=COALESCE(?,stock),image_url=COALESCE(?,image_url),active=COALESCE(?,active) WHERE id=?").run(name,category,price,stock,image_url,active,req.params.id);res.json({ok:true})});
app.post("/api/orders",auth,(req,res)=>{const {customer_name,phone,total,player_uid,items=[]}=req.body;const tx=db.transaction(()=>{const o=db.prepare("INSERT INTO orders(user_id,customer_name,phone,total,player_uid) VALUES(?,?,?,?,?)").run(req.user.id,customer_name,phone,total,player_uid||null);const s=db.prepare("INSERT INTO order_items(order_id,product_id,name,qty,unit_price) VALUES(?,?,?,?,?)");for(const i of items)s.run(o.lastInsertRowid,i.product_id,i.name,i.qty,i.unit_price);return o.lastInsertRowid});res.json({order_id:tx()})});
app.get("/api/orders",auth,(req,res)=>res.json(db.prepare("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC").all(req.user.id)));
app.get("/api/admin/orders",auth,admin,(req,res)=>res.json(db.prepare("SELECT * FROM orders ORDER BY id DESC").all()));
app.patch("/api/admin/orders/:id",auth,admin,(req,res)=>{db.prepare("UPDATE orders SET status=COALESCE(?,status),payment_status=COALESCE(?,payment_status) WHERE id=?").run(req.body.status,req.body.payment_status,req.params.id);res.json({ok:true})});
app.post("/api/coupons",auth,admin,(req,res)=>{const {code,discount_type,discount_value}=req.body;db.prepare("INSERT INTO coupons(code,discount_type,discount_value) VALUES(?,?,?)").run(code,discount_type,discount_value);res.json({ok:true})});
app.use(express.static(path.join(__dirname,"../frontend")));
app.listen(process.env.PORT||3000,()=>console.log("ELCAYSAR running"));
