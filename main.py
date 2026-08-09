import os
import csv
import io
import json
from datetime import datetime, date, timedelta
from typing import Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from config import CONFIG
from database import (
    init_db, create_user, get_user_by_username, get_user_by_id, get_all_users,
    update_user_profile, update_user_password,
    get_categories, create_category, delete_category,
    get_sources, get_source, create_source, delete_source, get_source_balance,
    get_cards, create_card, delete_card,
    create_transaction, get_transactions, get_transaction, update_transaction, delete_transaction,
    get_monthly_summary, get_yearly_summary,
    create_recurring_transaction, get_recurring_transactions, delete_recurring_transaction,
    generate_recurring_transactions,
    link_users, unlink_users, get_linked_users, get_linked_to_users, get_visible_user_ids,
    create_loan, get_loans, get_loan, delete_loan, get_loan_payments, update_loan_payment, get_loan_summary,
    get_setting, set_setting, get_all_settings,
    create_instance, get_user_instances, get_instance, get_instance_members,
    get_instance_transactions, create_instance_transaction,
    generate_instance_invite, join_instance_by_token, leave_instance,
    delete_instance, admin_remove_instance_member, get_instance_invites,
    is_instance_member, get_all_instances, update_instance_currency,
    admin_create_user, admin_delete_user, admin_reset_password,
    update_user_dashboard_instance, get_user_dashboard_instance,
    get_instance_view_config, update_instance_view_config,
    create_instance_wizard, update_instance_name, get_instance_by_id
)
SECRET_KEY = CONFIG["secret_key"]
APP_NAME = "Auditon"
HOST = CONFIG["host"]
PORT = CONFIG["port"]
LOGFILE = CONFIG["logfile"]
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
sessions = {}
def create_session(user_id: int) -> str:
    import secrets
    session_id = secrets.token_urlsafe(32)
    sessions[session_id] = {"user_id": user_id, "created_at": datetime.now()}
    return session_id
def get_session_user(request: Request) -> Optional[dict]:
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        session = sessions[session_id]
        if datetime.now() - session["created_at"] < timedelta(days=CONFIG["session_timeout_days"]):
            user = get_user_by_id(session["user_id"])
            if user:
                return {"id": user.id, "username": user.username, "is_admin": user.is_admin, "profile_picture": user.profile_picture, "profile_name": user.profile_name}
        else:
            del sessions[session_id]
    return None
async def require_auth(request: Request):
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user
def get_user_currency(user_id: int) -> str:
    instances = get_user_instances(user_id)
    if instances:
        dash = get_user_dashboard_instance(user_id)
        if dash:
            for inst in instances:
                if inst.get("id") == dash:
                    return inst.get("currency", "$")
        return instances[0].get("currency", "$")
    return "$"
def get_template_context(request, user, **extra):
    settings = get_all_settings(user["id"])
    instance_id = extra.get("instance_id")
    if instance_id:
        inst = get_instance(instance_id, user["id"])
        currency = inst.get("currency", "$") if inst else get_user_currency(user["id"])
    else:
        currency = get_user_currency(user["id"])
    ctx = {
        "request": request, "user": user, "app_name": APP_NAME,
        "currency": currency,
        "user_instances": get_user_instances(user["id"]),
        "settings": settings
    }
    ctx.update(extra)
    return ctx
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    generate_recurring_transactions()
    yield
app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    if get_session_user(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "app_name": APP_NAME, "currency": "$", "settings": {}})
@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = get_user_by_username(username)
    if not user or not pwd_context.verify(password, user.password_hash):
        return RedirectResponse(url="/login?error=Invalid credentials", status_code=302)
    session_id = create_session(user.id)
    homepage = get_setting(user.id, "homepage", "/")
    response = RedirectResponse(url=homepage, status_code=302)
    response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=604800)
    return response
@app.get("/logout")
async def logout(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        del sessions[session_id]
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_id")
    return response
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: Optional[str] = None):
    user = get_session_user(request)
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return templates.TemplateResponse("register.html", {"request": request, "error": error, "app_name": APP_NAME, "currency": "$", "admin_mode": True, "settings": {}})
@app.post("/register")
async def register(request: Request, username: str = Form(...), password: str = Form(...), confirm: str = Form(...)):
    user = get_session_user(request)
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    if password != confirm:
        return RedirectResponse(url="/register?error=Passwords do not match", status_code=302)
    if len(password) < 4:
        return RedirectResponse(url="/register?error=Password too short", status_code=302)
    if get_user_by_username(username):
        return RedirectResponse(url="/register?error=Username exists", status_code=302)
    admin_create_user(username, pwd_context.hash(password))
    return RedirectResponse(url="/settings?user_created=1", status_code=302)
@app.get("/")
async def root_redirect(request: Request, user: dict = Depends(require_auth)):
    instances = get_user_instances(user["id"])
    if not instances:
        return RedirectResponse(url="/no-instance", status_code=302)
    dash_inst = get_user_dashboard_instance(user["id"])
    if dash_inst:
        for inst in instances:
            if inst["id"] == dash_inst:
                return RedirectResponse(url=f"/instances/{dash_inst}", status_code=302)
    return RedirectResponse(url=f"/instances/{instances[0]['id']}", status_code=302)
@app.get("/no-instance", response_class=HTMLResponse)
async def no_instance_page(request: Request, user: dict = Depends(require_auth)):
    instances = get_user_instances(user["id"])
    if instances:
        return RedirectResponse(url="/", status_code=302)
    all_users = get_all_users() if user.get("is_admin") else []
    return templates.TemplateResponse("no_instance.html", get_template_context(
        request, user, all_users=all_users
    ))
@app.post("/no-instance/request")
async def request_collab(request: Request, message: str = Form(""), user: dict = Depends(require_auth)):
    return RedirectResponse(url="/no-instance?requested=1", status_code=302)
@app.get("/wizard", response_class=HTMLResponse)
async def wizard_page(request: Request, user: dict = Depends(require_auth)):
    all_users = get_all_users() if user.get("is_admin") else []
    return templates.TemplateResponse("wizard.html", get_template_context(
        request, user, all_users=all_users, today=date.today().isoformat()
    ))
@app.post("/wizard")
async def wizard_submit(
    request: Request,
    name: str = Form(...),
    currency: str = Form("$"),
    member_ids: str = Form(""),
    source_names: str = Form(""),
    expense_cats: str = Form(""),
    income_cats: str = Form(""),
    loan_count: int = Form(0),
    user: dict = Depends(require_auth)
):
    form_data = await request.form()
    mids = [int(x.strip()) for x in member_ids.split(",") if x.strip().isdigit()]
    srcs = [x.strip() for x in source_names.split("\n") if x.strip()]
    ecats = []
    for line in expense_cats.split("\n"):
        line = line.strip()
        if line:
            parts = line.split("|")
            ecats.append({"name": parts[0].strip(), "color": parts[1].strip() if len(parts) > 1 else "#6366f1", "is_income": False})
    icats = []
    for line in income_cats.split("\n"):
        line = line.strip()
        if line:
            parts = line.split("|")
            icats.append({"name": parts[0].strip(), "color": parts[1].strip() if len(parts) > 1 else "#10b981", "is_income": True})
    loans = []
    for i in range(loan_count):
        lname = form_data.get(f"loan_name_{i}", "")
        if lname and lname.strip():
            loans.append({
                "name": lname.strip(),
                "total_amount": float(form_data.get(f"loan_amount_{i}", 0) or 0),
                "tenure_months": int(form_data.get(f"loan_tenure_{i}", 0) or 0),
                "monthly_due": float(form_data.get(f"loan_monthly_{i}", 0) or 0),
                "start_date": form_data.get(f"loan_start_{i}", str(date.today())),
                "description": form_data.get(f"loan_desc_{i}", "")
            })
    instance_id = create_instance_wizard(user["id"], name, currency, mids, srcs, ecats + icats, loans)
    return RedirectResponse(url=f"/instances/{instance_id}?wizard=1", status_code=302)
@app.get("/transactions", response_class=HTMLResponse)
async def transactions_page(
    request: Request,
    filter_type: Optional[str] = None,
    filter_company: Optional[str] = None,
    filter_source: Optional[int] = None,
    filter_instance: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    is_company = None
    if filter_company == "yes": is_company = True
    elif filter_company == "no": is_company = False
    transactions = get_transactions(
        user_id=user["id"],
        start_date=start_date, end_date=end_date,
        is_company=is_company,
        source_id=filter_source,
        instance_id=filter_instance,
        transaction_type=filter_type if filter_type in ("expense", "income", "transfer") else None
    )
    return templates.TemplateResponse("transactions.html", get_template_context(
        request, user,
        transactions=transactions,
        categories=get_categories(user["id"]),
        sources=get_sources(user["id"]),
        instances=get_user_instances(user["id"]),
        filter_type=filter_type,
        filter_company=filter_company,
        filter_source=filter_source,
        filter_instance=filter_instance,
        start_date=start_date,
        end_date=end_date,
        instance_id=filter_instance
    ))
@app.get("/add", response_class=HTMLResponse)
async def add_transaction_page(request: Request, user: dict = Depends(require_auth)):
    instances = get_user_instances(user["id"])
    if not instances:
        return RedirectResponse(url="/no-instance", status_code=302)
    return templates.TemplateResponse("add_transaction.html", get_template_context(
        request, user,
        categories=get_categories(user["id"]),
        sources=get_sources(user["id"]),
        instances=instances,
        today=date.today().isoformat()
    ))
@app.post("/add")
async def add_transaction(
    request: Request,
    amount: float = Form(...),
    description: str = Form(...),
    category_id: Optional[int] = Form(None),
    source_id: Optional[int] = Form(None),
    to_source_id: Optional[int] = Form(None),
    tags: str = Form(""),
    transaction_type: str = Form("expense"),
    is_company: bool = Form(False),
    date: str = Form(...),
    instance_id: int = Form(...),
    user: dict = Depends(require_auth)
):
    instances = get_user_instances(user["id"])
    if not instances:
        return RedirectResponse(url="/no-instance", status_code=302)
    if not is_instance_member(instance_id, user["id"]):
        return RedirectResponse(url="/add?error=Invalid instance", status_code=302)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    create_transaction(
        user_id=user["id"], instance_id=instance_id, amount=amount, description=description,
        category_id=category_id, source_id=source_id, to_source_id=to_source_id,
        tags=tag_list, transaction_type=transaction_type,
        is_company=is_company, date=date
    )
    curr = get_user_currency(user["id"])
    sign = "+" if transaction_type == "income" else ("->" if transaction_type == "transfer" else "-")
    toast_msg = f"{sign}{curr}{amount:.2f} - {description} on {date}"
    return RedirectResponse(url=f"/instances/{instance_id}?toast={toast_msg}", status_code=302)
@app.get("/edit/{transaction_id}", response_class=HTMLResponse)
async def edit_transaction_page(transaction_id: int, request: Request, user: dict = Depends(require_auth)):
    transaction = get_transaction(transaction_id, user["id"])
    if not transaction:
        raise HTTPException(status_code=404, detail="Not found")
    return templates.TemplateResponse("edit_transaction.html", get_template_context(
        request, user,
        transaction=transaction,
        categories=get_categories(user["id"]),
        sources=get_sources(user["id"]),
        instances=get_user_instances(user["id"])
    ))
@app.post("/edit/{transaction_id}")
async def edit_transaction(
    transaction_id: int, request: Request,
    amount: float = Form(...), description: str = Form(...),
    category_id: Optional[int] = Form(None),
    source_id: Optional[int] = Form(None),
    to_source_id: Optional[int] = Form(None),
    tags: str = Form(""),
    transaction_type: str = Form("expense"),
    is_company: bool = Form(False),
    date: str = Form(...),
    instance_id: int = Form(...),
    user: dict = Depends(require_auth)
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    update_transaction(
        transaction_id=transaction_id, user_id=user["id"],
        amount=amount, description=description,
        category_id=category_id, source_id=source_id, to_source_id=to_source_id,
        tags=tag_list, transaction_type=transaction_type,
        is_company=is_company, date=date, instance_id=instance_id
    )
    tx = get_transaction(transaction_id, user["id"])
    inst_id = tx.get("instance_id") if tx else None
    if inst_id:
        return RedirectResponse(url=f"/instances/{inst_id}?toast=Transaction+updated", status_code=302)
    return RedirectResponse(url="/transactions", status_code=302)
@app.get("/delete/{transaction_id}")
async def delete_transaction_route(transaction_id: int, user: dict = Depends(require_auth)):
    delete_transaction(transaction_id, user["id"])
    return RedirectResponse(url="/transactions", status_code=302)
@app.get("/categories", response_class=HTMLResponse)
async def categories_page(request: Request, instance_id: Optional[int] = None, user: dict = Depends(require_auth)):
    return templates.TemplateResponse("categories.html", get_template_context(
        request, user, categories=get_categories(user["id"], instance_id=instance_id), instance_id=instance_id
    ))
@app.post("/categories/add")
async def add_category(request: Request, name: str = Form(...), color: str = Form("#6366f1"), is_income: bool = Form(False), instance_id: Optional[int] = Form(None), user: dict = Depends(require_auth)):
    create_category(user["id"], name, color, is_income, instance_id=instance_id)
    if instance_id:
        return RedirectResponse(url=f"/instances/{instance_id}?toast=Category+added", status_code=302)
    return RedirectResponse(url="/categories", status_code=302)
@app.get("/categories/delete/{category_id}")
async def delete_category_route(category_id: int, user: dict = Depends(require_auth)):
    if not delete_category(category_id, user["id"]):
        return RedirectResponse(url="/categories?error=Category in use", status_code=302)
    return RedirectResponse(url="/categories", status_code=302)
@app.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request, instance_id: Optional[int] = None, user: dict = Depends(require_auth)):
    sources = get_sources(user["id"], instance_id=instance_id)
    source_balances = [{"source": s, "balance": get_source_balance(user["id"], s.id)} for s in sources]
    return templates.TemplateResponse("sources.html", get_template_context(
        request, user, sources=sources, source_balances=source_balances, instance_id=instance_id
    ))
@app.post("/sources/add")
async def add_source(request: Request, name: str = Form(...), source_type: str = Form("custom"), instance_id: Optional[int] = Form(None), user: dict = Depends(require_auth)):
    create_source(user["id"], name, source_type, instance_id=instance_id)
    if instance_id:
        return RedirectResponse(url=f"/instances/{instance_id}?toast=Source+added", status_code=302)
    return RedirectResponse(url="/sources", status_code=302)
@app.get("/sources/delete/{source_id}")
async def delete_source_route(source_id: int, user: dict = Depends(require_auth)):
    if not delete_source(source_id, user["id"]):
        return RedirectResponse(url="/sources?error=Source in use", status_code=302)
    return RedirectResponse(url="/sources", status_code=302)
@app.get("/cards", response_class=HTMLResponse)
async def cards_page(request: Request, instance_id: Optional[int] = None, user: dict = Depends(require_auth)):
    return templates.TemplateResponse("cards.html", get_template_context(
        request, user, cards=get_cards(user["id"], instance_id=instance_id), instance_id=instance_id
    ))
@app.post("/cards/add")
async def add_card(
    request: Request,
    name: str = Form(...),
    card_number: str = Form(...),
    cvv: str = Form(...),
    expiry_date: str = Form(...),
    card_holder: str = Form(""),
    bank_name: str = Form(""),
    color: str = Form("#6366f1"),
    instance_id: Optional[int] = Form(None),
    user: dict = Depends(require_auth)
):
    create_card(user["id"], name, card_number, cvv, expiry_date, card_holder, bank_name, color, instance_id=instance_id)
    if instance_id:
        return RedirectResponse(url=f"/instances/{instance_id}?toast=Card+added", status_code=302)
    return RedirectResponse(url="/cards", status_code=302)
@app.get("/cards/delete/{card_id}")
async def delete_card_route(card_id: int, user: dict = Depends(require_auth)):
    delete_card(card_id, user["id"])
    return RedirectResponse(url="/cards", status_code=302)
@app.get("/recurring", response_class=HTMLResponse)
async def recurring_page(request: Request, instance_id: Optional[int] = None, user: dict = Depends(require_auth)):
    return templates.TemplateResponse("recurring.html", get_template_context(
        request, user,
        recurring=get_recurring_transactions(user["id"], instance_id=instance_id),
        categories=get_categories(user["id"], instance_id=instance_id),
        sources=get_sources(user["id"], instance_id=instance_id),
        instance_id=instance_id
    ))
@app.post("/recurring/add")
async def add_recurring(
    request: Request,
    amount: float = Form(...), description: str = Form(...),
    category_id: Optional[int] = Form(None),
    source_id: Optional[int] = Form(None),
    tags: str = Form(""),
    is_income: bool = Form(False),
    is_company: bool = Form(False),
    frequency: str = Form(...),
    start_date: str = Form(...),
    end_date: Optional[str] = Form(None),
    instance_id: Optional[int] = Form(None),
    user: dict = Depends(require_auth)
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    create_recurring_transaction(
        user_id=user["id"], amount=amount, description=description,
        category_id=category_id, source_id=source_id, tags=tag_list,
        is_income=is_income, is_company=is_company,
        frequency=frequency, start_date=start_date, end_date=end_date,
        instance_id=instance_id
    )
    generate_recurring_transactions()
    if instance_id:
        return RedirectResponse(url=f"/instances/{instance_id}?toast=Recurring+added", status_code=302)
    return RedirectResponse(url="/recurring", status_code=302)
@app.get("/recurring/delete/{recurring_id}")
async def delete_recurring_route(recurring_id: int, user: dict = Depends(require_auth)):
    delete_recurring_transaction(recurring_id, user["id"])
    return RedirectResponse(url="/recurring", status_code=302)
@app.get("/reports", response_class=HTMLResponse)
async def reports_page(
    request: Request,
    year: Optional[int] = None, month: Optional[int] = None,
    view: str = "monthly",
    instance_id: Optional[int] = None,
    user: dict = Depends(require_auth)
):
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    if view == "yearly":
        summary = get_yearly_summary(user_id=user["id"], year=year)
    else:
        summary = get_monthly_summary(user_id=user["id"], year=year, month=month)
    return templates.TemplateResponse("reports.html", get_template_context(
        request, user,
        summary=summary, view=view, year=year, month=month,
        month_name=datetime(year, month, 1).strftime("%B") if month else "",
        instance_id=instance_id
    ))
@app.get("/export")
async def export_csv(user: dict = Depends(require_auth)):
    transactions = get_transactions(user_id=user["id"])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "category", "amount", "date", "tags"])
    for t in transactions:
        tags = ",".join(t["tags"]) if t["tags"] else ""
        writer.writerow([
            t["id"],
            t["description"],
            t.get("category_name", ""),
            f"{t['amount']:.2f}",
            t["date"],
            tags
        ])
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=auditon_{user['username']}_{date.today()}.csv"}
    )
@app.post("/import")
async def import_csv(request: Request, file: UploadFile = File(...), instance_id: Optional[int] = Form(None), user: dict = Depends(require_auth)):
    instances = get_user_instances(user["id"])
    if not instances:
        return RedirectResponse(url="/no-instance", status_code=302)
    use_instance = instance_id if instance_id else instances[0]["id"]
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    categories = get_categories(user["id"])
    cat_map = {c.name: c.id for c in categories}
    sources = get_sources(user["id"])
    src_map = {s.name: s.id for s in sources}
    imported = 0
    for row in reader:
        try:
            amount = float(row["amount"])
            description = row["name"]
            date_str = row["date"]
            if amount < 0:
                ttype = "expense"
                amount = abs(amount)
            else:
                ttype = "income"
            cat_name = row.get("category", "")
            category_id = cat_map.get(cat_name)
            if cat_name and not category_id:
                category_id = create_category(user["id"], cat_name, "#6366f1", False)
                cat_map[cat_name] = category_id
                categories = get_categories(user["id"])
                cat_map = {c.name: c.id for c in categories}
            tags = [t.strip() for t in row.get("tags", "").split(",") if t.strip()]
            create_transaction(
                user_id=user["id"], instance_id=use_instance, amount=amount, description=description,
                category_id=category_id, source_id=None, to_source_id=None,
                tags=tags, transaction_type=ttype,
                is_company=False, date=date_str
            )
            imported += 1
        except Exception:
            continue
    return RedirectResponse(url=f"/instances/{use_instance}?toast=Imported+{imported}+transactions", status_code=302)
@app.get("/loans", response_class=HTMLResponse)
async def loans_page(request: Request, instance_id: Optional[int] = None, user: dict = Depends(require_auth)):
    loans = get_loans(user["id"], instance_id=instance_id)
    loan_summary = get_loan_summary(user["id"])
    return templates.TemplateResponse("loans.html", get_template_context(
        request, user, loans=loans, loan_summary=loan_summary, instance_id=instance_id
    ))
@app.post("/loans/add")
async def add_loan(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    total_amount: float = Form(...),
    tenure_months: int = Form(...),
    monthly_due: float = Form(...),
    start_date: str = Form(...),
    instance_id: Optional[int] = Form(None),
    user: dict = Depends(require_auth)
):
    create_loan(user["id"], name, description, total_amount, tenure_months, monthly_due, start_date, instance_id=instance_id)
    if instance_id:
        return RedirectResponse(url=f"/instances/{instance_id}?toast=Loan+added", status_code=302)
    return RedirectResponse(url="/loans", status_code=302)
@app.get("/loans/delete/{loan_id}")
async def delete_loan_route(loan_id: int, user: dict = Depends(require_auth)):
    delete_loan(loan_id, user["id"])
    return RedirectResponse(url="/loans", status_code=302)
@app.get("/loans/{loan_id}", response_class=HTMLResponse)
async def loan_detail_page(loan_id: int, request: Request, user: dict = Depends(require_auth)):
    loan = get_loan(loan_id, user["id"])
    if not loan:
        raise HTTPException(status_code=404, detail="Not found")
    payments = get_loan_payments(loan_id)
    return templates.TemplateResponse("loan_detail.html", get_template_context(
        request, user, loan=loan, payments=payments,
        instance_id=loan.get("instance_id")
    ))
@app.post("/loans/{loan_id}/pay")
async def pay_loan(
    loan_id: int, request: Request,
    payment_ids: str = Form(...),
    status: str = Form(...),
    description: str = Form(""),
    user: dict = Depends(require_auth)
):
    for pid in payment_ids.split(","):
        if pid.strip():
            update_loan_payment(int(pid.strip()), status, description)
    return RedirectResponse(url=f"/loans/{loan_id}", status_code=302)
@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, user: dict = Depends(require_auth)):
    settings = get_all_settings(user["id"])
    all_users = get_all_users() if user.get("is_admin") else []
    instances = get_user_instances(user["id"])
    import json
    instance_views = {}
    try:
        instance_views = json.loads(settings.get("instance_views", "{}"))
    except:
        instance_views = {}
    return templates.TemplateResponse("settings.html", get_template_context(
        request, user,
        settings=settings,
        categories=get_categories(user["id"]),
        all_users=all_users,
        instances=instances,
        instance_views=instance_views
    ))
@app.post("/settings")
async def update_settings(
    request: Request,
    theme: str = Form("light"),
    language: str = Form("en"),
    date_format: str = Form("YYYY-MM-DD"),
    font_family: str = Form("system"),
    font_size: str = Form("medium"),
    instance_views: str = Form("{}"),
    user: dict = Depends(require_auth)
):
    set_setting(user["id"], "theme", theme)
    set_setting(user["id"], "language", language)
    set_setting(user["id"], "date_format", date_format)
    set_setting(user["id"], "font_family", font_family)
    set_setting(user["id"], "font_size", font_size)
    set_setting(user["id"], "instance_views", instance_views)
    return RedirectResponse(url="/settings?saved=1", status_code=302)
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user: dict = Depends(require_auth)):
    user_data = get_user_by_id(user["id"])
    transactions = get_transactions(user_id=user["id"])
    categories = get_categories(user["id"])
    sources = get_sources(user["id"])
    cards = get_cards(user["id"])
    loans = get_loans(user["id"])
    stats = {
        "total_transactions": len(transactions),
        "total_categories": len(categories),
        "total_sources": len(sources),
        "total_cards": len(cards),
        "total_loans": len(loans)
    }
    return templates.TemplateResponse("profile.html", get_template_context(
        request, user,
        user_data=user_data,
        stats=stats
    ))
@app.post("/profile")
async def update_profile(
    request: Request,
    username: str = Form(...),
    profile_name: str = Form(""),
    avatar_data: str = Form(""),
    user: dict = Depends(require_auth)
):
    existing = get_user_by_username(username)
    if existing and existing.id != user["id"]:
        return RedirectResponse(url="/profile?error=Username already taken", status_code=302)
    profile_picture = None
    if avatar_data and avatar_data.startswith("data:image"):
        upload_dir = "static/uploads/avatars"
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"user_{user['id']}.png"
        filepath = os.path.join(upload_dir, filename)
        header, encoded = avatar_data.split(",", 1)
        import base64
        content = base64.b64decode(encoded)
        with open(filepath, "wb") as f:
            f.write(content)
        profile_picture = f"/static/uploads/avatars/{filename}"
    update_user_profile(user["id"], username=username, profile_picture=profile_picture, profile_name=profile_name or None)
    user["username"] = username
    user["profile_name"] = profile_name or None
    return RedirectResponse(url="/profile?saved=1", status_code=302)

@app.post("/profile/remove_avatar")
async def remove_avatar(request: Request, user: dict = Depends(require_auth)):
    upload_dir = "static/uploads/avatars"
    for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        filepath = os.path.join(upload_dir, f"user_{user['id']}{ext}")
        if os.path.exists(filepath):
            os.remove(filepath)
    update_user_profile(user["id"], profile_picture="")
    user["profile_picture"] = None
    return {"ok": True}
@app.post("/profile/password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: dict = Depends(require_auth)
):
    user_data = get_user_by_id(user["id"])
    if not pwd_context.verify(current_password, user_data.password_hash):
        return RedirectResponse(url="/profile?error=Current password is incorrect", status_code=302)
    if new_password != confirm_password:
        return RedirectResponse(url="/profile?error=Passwords do not match", status_code=302)
    if len(new_password) < 4:
        return RedirectResponse(url="/profile?error=Password too short", status_code=302)
    update_user_password(user["id"], pwd_context.hash(new_password))
    return RedirectResponse(url="/profile?pass_changed=1", status_code=302)
@app.get("/instances", response_class=HTMLResponse)
async def instances_page(request: Request, user: dict = Depends(require_auth)):
    instances = get_user_instances(user["id"])
    if not instances:
        return RedirectResponse(url="/no-instance", status_code=302)
    return templates.TemplateResponse("instances.html", get_template_context(
        request, user, instances=instances
    ))
@app.post("/instances/add")
async def add_instance(request: Request, name: str = Form(...), currency: str = Form("$"), user: dict = Depends(require_auth)):
    create_instance(user["id"], name, currency)
    return RedirectResponse(url="/instances", status_code=302)
@app.get("/instances/{instance_id}", response_class=HTMLResponse)
async def instance_detail_page(instance_id: int, request: Request, user: dict = Depends(require_auth)):
    if not is_instance_member(instance_id, user["id"]):
        raise HTTPException(status_code=403, detail="Not a member")
    inst = get_instance(instance_id, user["id"])
    if not inst:
        raise HTTPException(status_code=404, detail="Not found")
    members = get_instance_members(instance_id)
    transactions = get_instance_transactions(instance_id)
    sources = get_sources(user["id"], instance_id=instance_id)
    categories = get_categories(user["id"], instance_id=instance_id)
    cards = get_cards(user["id"], instance_id=instance_id)
    recurring = get_recurring_transactions(user["id"], instance_id=instance_id)
    loans = get_loans(user["id"], instance_id=instance_id)
    invites = get_instance_invites(instance_id) if inst["role"] == "owner" else []
    total_income = sum(t["amount"] for t in transactions if t.get("transaction_type") == "income")
    total_expenses = sum(t["amount"] for t in transactions if t.get("transaction_type") == "expense")
    total_company = sum(t["amount"] for t in transactions if t.get("is_company") and t.get("transaction_type") == "expense")
    source_balances = []
    for s in sources:
        bal = get_source_balance(user["id"], s.id)
        source_balances.append({"source": s, "balance": bal})
    from collections import defaultdict
    cat_totals = defaultdict(lambda: {"total": 0, "color": "#6366f1"})
    for t in transactions:
        if t.get("category_name"):
            cat_totals[t["category_name"]]["total"] += t["amount"]
            cat_totals[t["category_name"]]["color"] = t.get("category_color", "#6366f1")
    category_data = {
        "labels": list(cat_totals.keys())[:8],
        "values": [cat_totals[k]["total"] for k in list(cat_totals.keys())[:8]],
        "colors": [cat_totals[k]["color"] for k in list(cat_totals.keys())[:8]]
    } if cat_totals else None
    for loan in loans:
        loan["progress_percent"] = (loan.get("paid_count", 0) / loan["tenure_months"] * 100) if loan["tenure_months"] else 0
    view_config = get_instance_view_config(instance_id)
    if not view_config:
        view_config = {
            "transactions": True, "cards": True, "sources": True,
            "categories": True, "recurring": True, "loans": True, "reports": True
        }
    return templates.TemplateResponse("instance_detail.html", get_template_context(
        request, user,
        instance=inst,
        members=members,
        transactions=transactions[:20],
        sources=sources,
        categories=categories,
        cards=cards,
        recurring=recurring,
        loans=loans,
        source_balances=source_balances,
        summary={"income": total_income, "expenses": total_expenses, "net": total_income - total_expenses, "company": total_company},
        category_data=category_data,
        invites=invites,
        today=date.today().isoformat(),
        view_config=view_config
    ))
@app.post("/instances/{instance_id}/invite")
async def create_invite(instance_id: int, request: Request, user: dict = Depends(require_auth)):
    inst = get_instance(instance_id, user["id"])
    if not inst or inst["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner only")
    token = generate_instance_invite(instance_id, user["id"])
    invite_url = f"{request.base_url}join/{token}"
    return RedirectResponse(url=f"/instances/{instance_id}?invite={invite_url}", status_code=302)
@app.get("/join/{token}")
async def join_page(token: str, request: Request, user: dict = Depends(require_auth)):
    result = join_instance_by_token(token, user["id"])
    if result:
        return RedirectResponse(url=f"/instances/{result['instance_id']}?joined=1", status_code=302)
    return RedirectResponse(url="/instances?error=Invalid or expired invite", status_code=302)
@app.get("/instances/{instance_id}/leave")
async def leave_instance_route(instance_id: int, user: dict = Depends(require_auth)):
    leave_instance(instance_id, user["id"])
    return RedirectResponse(url="/instances", status_code=302)
@app.get("/instances/{instance_id}/delete")
async def delete_instance_route(instance_id: int, user: dict = Depends(require_auth)):
    if not delete_instance(instance_id, user["id"]):
        raise HTTPException(status_code=403, detail="Owner only")
    return RedirectResponse(url="/instances", status_code=302)
@app.get("/instances/{instance_id}/remove/{member_user_id}")
async def remove_member_route(instance_id: int, member_user_id: int, request: Request, user: dict = Depends(require_auth)):
    inst = get_instance(instance_id, user["id"])
    if not inst:
        raise HTTPException(status_code=404, detail="Not found")
    if inst["role"] == "owner" or user.get("is_admin"):
        admin_remove_instance_member(instance_id, member_user_id)
        return RedirectResponse(url=f"/instances/{instance_id}", status_code=302)
    raise HTTPException(status_code=403, detail="Not allowed")
@app.get("/instances/{instance_id}/edit_currency", response_class=HTMLResponse)
async def edit_currency_page(instance_id: int, request: Request, user: dict = Depends(require_auth)):
    inst = get_instance(instance_id, user["id"])
    if not inst or inst["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner only")
    return templates.TemplateResponse("edit_currency.html", get_template_context(
        request, user, instance=inst
    ))
@app.post("/instances/{instance_id}/edit_currency")
async def edit_currency(instance_id: int, request: Request, currency: str = Form(...), conversion_rate: float = Form(1.0), confirm: bool = Form(False), user: dict = Depends(require_auth)):
    if not confirm:
        return RedirectResponse(url=f"/instances/{instance_id}/edit_currency?error=Please confirm currency change", status_code=302)
    if not update_instance_currency(instance_id, user["id"], currency, conversion_rate):
        raise HTTPException(status_code=403, detail="Owner only")
    return RedirectResponse(url=f"/instances/{instance_id}?toast=Currency+updated", status_code=302)
@app.get("/instances/{instance_id}/settings", response_class=HTMLResponse)
async def instance_settings_page(instance_id: int, request: Request, user: dict = Depends(require_auth)):
    inst = get_instance(instance_id, user["id"])
    if not inst:
        raise HTTPException(status_code=404, detail="Not found")
    if inst["role"] != "owner" and not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Owner only")
    members = get_instance_members(instance_id)
    all_users = get_all_users() if user.get("is_admin") else []
    view_config = get_instance_view_config(instance_id)
    if not view_config:
        view_config = {
            "transactions": True, "cards": True, "sources": True,
            "categories": True, "recurring": True, "loans": True, "reports": True
        }
    return templates.TemplateResponse("instance_settings.html", get_template_context(
        request, user, instance=inst, members=members, all_users=all_users, view_config=view_config
    ))
@app.post("/instances/{instance_id}/settings")
async def instance_settings_post(
    instance_id: int, request: Request,
    name: str = Form(...),
    currency: str = Form("$"),
    view_transactions: bool = Form(False),
    view_cards: bool = Form(False),
    view_sources: bool = Form(False),
    view_categories: bool = Form(False),
    view_recurring: bool = Form(False),
    view_loans: bool = Form(False),
    view_reports: bool = Form(False),
    user: dict = Depends(require_auth)
):
    inst = get_instance(instance_id, user["id"])
    if not inst or (inst["role"] != "owner" and not user.get("is_admin")):
        raise HTTPException(status_code=403, detail="Owner only")
    update_instance_name(instance_id, name)
    update_instance_currency(instance_id, user["id"], currency, 1.0)
    view_config = {
        "transactions": view_transactions, "cards": view_cards, "sources": view_sources,
        "categories": view_categories, "recurring": view_recurring, "loans": view_loans, "reports": view_reports
    }
    update_instance_view_config(instance_id, view_config)
    return RedirectResponse(url=f"/instances/{instance_id}/settings?saved=1", status_code=302)
@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, user: dict = Depends(require_auth)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    users = get_all_users()
    instances = get_all_instances()
    cfg = dict(CONFIG)
    if not cfg.get("database_folder") or not str(cfg.get("database_folder")).strip():
        cfg["database_folder"] = "data"
    return templates.TemplateResponse("admin_users.html", get_template_context(
        request, user, users=users, instances=instances, config=cfg
    ))
@app.post("/admin/users/add")
async def admin_add_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    user: dict = Depends(require_auth)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    if get_user_by_username(username):
        return RedirectResponse(url="/admin/users?error=Username exists", status_code=302)
    admin_create_user(username, pwd_context.hash(password))
    return RedirectResponse(url="/admin/users?created=1", status_code=302)
@app.get("/admin/users/delete/{user_id}")
async def admin_delete_user_route(user_id: int, user: dict = Depends(require_auth)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    admin_delete_user(user_id)
    return RedirectResponse(url="/admin/users?deleted=1", status_code=302)
@app.post("/admin/users/reset/{user_id}")
async def admin_reset_user_password(user_id: int, request: Request, password: str = Form(...), user: dict = Depends(require_auth)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    admin_reset_password(user_id, pwd_context.hash(password))
    return RedirectResponse(url="/admin/users?reset=1", status_code=302)
@app.get("/admin/instances", response_class=HTMLResponse)
async def admin_instances_page(request: Request, user: dict = Depends(require_auth)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    instances = get_all_instances()
    return templates.TemplateResponse("admin_instances.html", get_template_context(
        request, user, instances=instances
    ))
@app.post("/admin/config")
async def admin_update_config(
    request: Request,
    host: str = Form(...),
    port: int = Form(...),
    database_folder: str = Form(...),
    logfile: str = Form(""),
    session_timeout_days: int = Form(...),
    secret_key: str = Form(...),
    user: dict = Depends(require_auth)
):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    from config import save_config
    save_config({
        "host": host,
        "port": port,
        "database_folder": database_folder,
        "logfile": logfile if logfile else None,
        "session_timeout_days": session_timeout_days,
        "secret_key": secret_key
    })
    return RedirectResponse(url="/admin/users?config_saved=1", status_code=302)
@app.get("/api/summary")
async def api_summary(year: int, month: Optional[int] = None, user_id: Optional[int] = None, user: dict = Depends(require_auth)):
    return get_monthly_summary(user_id=user_id, year=year, month=month)
@app.get("/api/transactions")
async def api_transactions(start_date: Optional[str] = None, end_date: Optional[str] = None,
                           is_company: Optional[bool] = None, user: dict = Depends(require_auth)):
    return get_transactions(user_id=user["id"], start_date=start_date, end_date=end_date, is_company=is_company)
if __name__ == "__main__":
    import uvicorn
    if LOGFILE:
        import logging
        logging.basicConfig(filename=LOGFILE, level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    print(f"Starting Auditon on http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)