from sqlalchemy.orm import Session
from .models import Worker, Account, SessionLocal

def get_db():
    """Функция для получения сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Операции с воркерами
def create_worker(db: Session, name: str, server_address: str):
    """Создание нового воркера"""
    worker = Worker(name=name, server_address=server_address)
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker

def get_worker(db: Session, worker_id: int):
    """Получение воркера по ID"""
    return db.query(Worker).filter(Worker.id == worker_id).first()

def get_worker_by_name(db: Session, name: str):
    """Получение воркера по имени"""
    return db.query(Worker).filter(Worker.name == name).first()

def get_all_workers(db: Session, active_only: bool = False):
    """Получение всех воркеров"""
    query = db.query(Worker)
    if active_only:
        query = query.filter(Worker.is_active == True)
    return query.all()

def update_worker_status(db: Session, worker_id: int, is_active: bool):
    """Обновление статуса воркера"""
    worker = get_worker(db, worker_id)
    if worker:
        worker.is_active = is_active
        db.commit()
        db.refresh(worker)
    return worker

def delete_worker(db: Session, worker_id: int):
    """Удаление воркера"""
    worker = get_worker(db, worker_id)
    if worker:
        # Удаляем связанные аккаунты
        for account in worker.accounts:
            db.delete(account)
        db.delete(worker)
        db.commit()
        return True
    return False

# Операции с аккаунтами
def create_account(db: Session, phone: str, api_id: str, api_hash: str, worker_id: int, session_string: str = None):
    """Создание нового аккаунта"""
    account = Account(
        phone=phone,
        api_id=api_id,
        api_hash=api_hash,
        worker_id=worker_id,
        session_string=session_string
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account

def get_account(db: Session, account_id: int):
    """Получение аккаунта по ID"""
    return db.query(Account).filter(Account.id == account_id).first()

def get_account_by_phone(db: Session, phone: str):
    """Получение аккаунта по номеру телефона"""
    return db.query(Account).filter(Account.phone == phone).first()

def get_worker_accounts(db: Session, worker_id: int, active_only: bool = False):
    """Получение всех аккаунтов воркера"""
    query = db.query(Account).filter(Account.worker_id == worker_id)
    if active_only:
        query = query.filter(Account.is_active == True)
    return query.all()

def update_account_status(db: Session, account_id: int, is_active: bool):
    """Обновление статуса аккаунта"""
    account = get_account(db, account_id)
    if account:
        account.is_active = is_active
        db.commit()
        db.refresh(account)
    return account

def update_account_session(db: Session, account_id: int, session_string: str):
    """Обновление строки сессии аккаунта"""
    account = get_account(db, account_id)
    if account:
        account.session_string = session_string
        db.commit()
        db.refresh(account)
    return account

def get_all_accounts(db: Session, active_only: bool = False):
    """Получение всех аккаунтов"""
    query = db.query(Account)
    if active_only:
        query = query.filter(Account.is_active == True)
    return query.all() 