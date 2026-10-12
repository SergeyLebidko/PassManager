"""Модульные тесты PassManager.

Запуск из каталога проекта:
    python -m app.tests.test_core
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Позволяем запускать как отдельный скрипт.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import crypto, storage
from app.export import build_txt
from app.manager import Manager
from app.models import Account, HistoryEntry, Service, Vault
from app.sync import merge


def test_crypto_roundtrip() -> None:
    password = "master-pass"
    salt = crypto.new_salt()
    key = crypto.derive_key(password, salt)
    payload = json.dumps({"hello": "мир"}).encode("utf-8")
    text = crypto.encrypt_bytes(key, payload, salt)
    plaintext, salt2, iters2 = crypto.decrypt_text(password, text)
    assert plaintext == payload
    assert salt2 == salt


def test_crypto_wrong_password() -> None:
    salt = crypto.new_salt()
    key = crypto.derive_key("correct", salt)
    text = crypto.encrypt_bytes(key, b"secret", salt)
    try:
        crypto.decrypt_text("wrong", text)
    except crypto.WrongPasswordError:
        return
    raise AssertionError("Ожидалась ошибка WrongPasswordError")


def test_storage_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "vault.txt"
        salt = crypto.new_salt()
        key = crypto.derive_key("pw", salt)
        vault = Vault.empty()
        svc = Service(name="Gmail")
        acc = Account(title="Личный", login="user@mail", password="p@ss")
        svc.accounts.append(acc)
        vault.services.append(svc)

        storage.save_vault(vault, key, salt, path=path)
        loaded, key2, salt2, iters2 = storage.load_vault("pw", path=path)
        assert key2 == key
        assert loaded.services[0].name == "Gmail"
        assert loaded.services[0].accounts[0].login == "user@mail"


def test_merge_newer_wins() -> None:
    a = Vault.empty()
    svc = Service(name="Bank")
    acc = Account(id="1", title="A", login="old", password="old", modified_at=100.0)
    svc.accounts.append(acc)
    a.services.append(svc)

    b = Vault.empty()
    svc2 = Service(id=svc.id, name="Bank")
    acc2 = Account(id="1", title="A", login="new", password="new", modified_at=200.0)
    svc2.accounts.append(acc2)
    b.services.append(svc2)

    merged = merge(a, b)
    assert merged.services[0].accounts[0].login == "new"


def test_merge_adds_from_both_sides() -> None:
    a = Vault.empty()
    a.services.append(Service(name="OnlyLocal"))
    b = Vault.empty()
    b.services.append(Service(name="OnlyRemote"))

    merged = merge(a, b)
    names = sorted(s.name for s in merged.services)
    assert names == ["OnlyLocal", "OnlyRemote"]


def test_merge_tombstone_removes() -> None:
    a = Vault.empty()
    svc = Service(name="ToDelete")
    a.services.append(svc)
    b = Vault.empty()
    b.tombstones.append(_tomb(svc.id))

    merged = merge(a, b)
    assert all(s.name != "ToDelete" for s in merged.services)


def _tomb(item_id: str):
    from app.models import Tombstone
    return Tombstone(id=item_id, deleted_at=1000.0)


def test_history_on_password_change() -> None:
    acc = Account(login="u", password="first")
    acc.change_password("second")
    assert acc.password == "second"
    assert len(acc.history) == 1
    assert acc.history[0].password == "first"
    assert acc.history[0].kind == "password"


def test_history_on_login_change() -> None:
    acc = Account(login="old@mail", password="p")
    acc.change_login("new@mail")
    assert acc.login == "new@mail"
    assert len(acc.history) == 1
    assert acc.history[0].login == "old@mail"
    assert acc.history[0].kind == "login"


def test_history_kind_persists() -> None:
    acc = Account(login="a", password="p")
    acc.change_login("b")
    acc.change_password("q")
    restored = Account.from_dict(acc.to_dict())
    kinds = [h.kind for h in restored.history]
    assert kinds == ["password", "login"], kinds
    # old format without "kind" defaults to "password"
    legacy = {"login": "a", "password": "x", "changed_at": 1.0}
    assert HistoryEntry.from_dict(legacy).kind == "password"
    assert restored.login_changed_at == acc.login_changed_at


def test_trash_and_restore() -> None:
    vault = Vault.empty()
    svc = Service(name="S")
    acc = Account(title="Acc", login="l", password="p")
    svc.accounts.append(acc)
    vault.services.append(svc)

    vault.trash_account(svc, acc)
    assert len(svc.accounts) == 0
    assert len(vault.trash) == 1

    vault.restore(vault.trash[0])
    assert len(vault.services[0].accounts) == 1


def test_restore_account_when_service_in_trash() -> None:
    """Удалили запись, затем сервис; восстановление записи должно вернуть
    сам сервис, а не создавать дубликат и не оставлять сервис в корзине."""
    vault = Vault.empty()
    svc = Service(name="Почта")
    acc = Account(title="Acc", login="l", password="p")
    svc.accounts.append(acc)
    vault.services.append(svc)

    vault.trash_account(svc, acc)      # удалили запись
    vault.trash_service(svc)           # затем сервис
    assert len(vault.services) == 0
    assert len(vault.trash) == 2

    account_item = next(t for t in vault.trash if t.kind == "account")
    vault.restore(account_item)

    # Сервис вернулся один (без дубликата) и ушёл из корзины вместе с записью.
    assert len(vault.services) == 1, [s.name for s in vault.services]
    assert vault.services[0].id == svc.id
    assert len(vault.services[0].accounts) == 1
    assert vault.trash == [], [(t.kind, t.name) for t in vault.trash]


def test_restore_service_merges_accounts() -> None:
    """Восстановление сервиса, который уже активен, добавляет недостающие записи."""
    vault = Vault.empty()
    svc = Service(name="S")
    acc1 = Account(title="A", login="a", password="p")
    acc2 = Account(title="B", login="b", password="p")
    svc.accounts.extend([acc1, acc2])
    vault.services.append(svc)

    # Сервис лежит в корзине целиком (с двумя записями)...
    vault.trash_service(svc)
    # ...а активный сервис с тем же id и одной записью появился заново.
    active = Service(id=svc.id, name="S")
    active.accounts.append(Account(id=acc1.id, title="A", login="a", password="p"))
    vault.services.append(active)

    service_item = next(t for t in vault.trash if t.kind == "service")
    vault.restore(service_item)

    assert len(vault.services) == 1
    ids = {a.id for a in vault.services[0].accounts}
    assert ids == {acc1.id, acc2.id}, ids


def test_purge_adds_tombstone() -> None:
    vault = Vault.empty()
    svc = Service(name="S")
    vault.services.append(svc)
    vault.trash_service(svc)
    item = vault.trash[0]
    vault.purge(item)
    assert not vault.trash
    assert any(t.id == svc.id for t in vault.tombstones)


def test_export_txt_contains_all_fields() -> None:
    vault = Vault.empty()
    svc = Service(name="Почта")
    acc = Account(title="Основная", login="user@mail.ru",
                  password="S3cret!", comment="рабочая")
    svc.accounts.append(acc)
    empty = Service(name="Пустой сервис")
    vault.services.extend([svc, empty])

    text = build_txt(vault)
    assert "СЕРВИС: Почта" in text
    assert "user@mail.ru" in text
    assert "S3cret!" in text
    assert "рабочая" in text
    assert "Основная" in text
    assert "СЕРВИС: Пустой сервис" in text
    assert "учётных записей нет" in text
    # Корзина в экспорт не попадает.
    vault.trash_account(svc, acc)
    assert "Основная" not in build_txt(vault)


def test_export_txt_empty_vault() -> None:
    text = build_txt(Vault.empty())
    assert "Список сервисов пуст" in text
    assert "Сервисов: 0" in text


def test_manager_unlock_flow() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        old_vault, old_cfg = storage.VAULT_FILE, storage.CONFIG_FILE
        storage.VAULT_FILE = Path(tmp) / "vault.txt"
        storage.CONFIG_FILE = Path(tmp) / "config.json"
        try:
            m = Manager()
            assert not m.has_local()
            m.create_new("secret1")
            assert m.has_local()

            m2 = Manager()
            m2.unlock("secret1")
            assert m2.vault.services == []
        finally:
            storage.VAULT_FILE, storage.CONFIG_FILE = old_vault, old_cfg


def run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"OK   {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc!r}")
    print(f"\nВсего: {len(tests)}, ошибок: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
