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
from app import export
from app import search
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


def test_history_on_title_and_comment_change() -> None:
    acc = Account(title="Старое", login="u", password="p", comment="старый коммент")
    acc.change_title("Новое")
    acc.change_comment("новый коммент")
    assert acc.title == "Новое"
    assert acc.comment == "новый коммент"
    kinds = [h.kind for h in acc.history]
    assert kinds == ["comment", "title"], kinds
    # Снимок хранит прежние значения.
    assert acc.history[0].comment == "старый коммент"
    assert acc.history[1].title == "Старое"


def test_history_title_comment_persist() -> None:
    acc = Account(title="t", login="u", password="p", comment="c")
    acc.change_title("t2")
    acc.change_comment("c2")
    restored = Account.from_dict(acc.to_dict())
    kinds = [h.kind for h in restored.history]
    assert kinds == ["comment", "title"], kinds
    assert restored.title_changed_at == acc.title_changed_at
    assert restored.comment_changed_at == acc.comment_changed_at
    # Старый формат без новых полей читается без ошибок.
    legacy = {"login": "u", "password": "p", "changed_at": 1.0}
    old = Account.from_dict(legacy)
    assert old.title_changed_at == old.created_at


def test_no_history_when_nothing_changed() -> None:
    acc = Account(title="t", login="u", password="p", comment="c")
    acc.change_title("t")
    acc.change_comment("c")
    acc.change_login("u")
    acc.change_password("p")
    assert acc.history == []


def test_search_service_name_and_account_fields() -> None:
    svc = Service(name="Gmail")
    acc = Account(title="Личная почта", login="user@gmail.com",
                  password="secret", comment="рабочая переписка")
    svc.accounts.append(acc)

    # По имени сервиса.
    assert search.service_matches(svc, "gmail")
    assert search.service_name_matches(svc, "GMAIL")
    # По названию записи.
    assert search.service_matches(svc, "личная")
    # По логину.
    assert search.service_matches(svc, "user@")
    # По комментарию.
    assert search.service_matches(svc, "переписк")
    # Нет совпадения.
    assert not search.service_matches(svc, "steam")


def test_search_ignores_password() -> None:
    svc = Service(name="Банк")
    svc.accounts.append(Account(title="Основная", login="l", password="topsecret"))
    assert not search.service_matches(svc, "topsecret")
    assert not search.account_matches(svc.accounts[0], "topsecret")


def test_search_matching_fields() -> None:
    acc = Account(title="Моя почта", login="me@mail.ru", comment="важное")
    assert search.matching_fields(acc, "почта") == {"title"}
    assert search.matching_fields(acc, "mail") == {"login"}
    assert search.matching_fields(acc, "важн") == {"comment"}
    assert search.matching_fields(acc, "me@mail.ru") == {"login"}
    assert search.matching_fields(acc, "") == set()


def test_search_empty_and_counts() -> None:
    svc = Service(name="Почта")
    svc.accounts.append(Account(title="A", login="a@a", comment=""))
    svc.accounts.append(Account(title="B", login="b@b", comment="нужное"))
    # Пустой запрос показывает всё.
    assert search.service_matches(svc, "  ")
    assert search.matched_account_count(svc, "") == 0
    # Считаем только совпавшие записи.
    assert search.matched_account_count(svc, "нужное") == 1


def test_delete_account_adds_tombstone() -> None:
    vault = Vault.empty()
    svc = Service(name="S")
    acc = Account(id="a1", title="Acc", login="l", password="p")
    svc.accounts.append(acc)
    vault.services.append(svc)

    vault.delete_account(svc, acc)
    assert svc.accounts == []
    assert any(t.id == "a1" for t in vault.tombstones)


def test_delete_service_removes_service_and_accounts() -> None:
    vault = Vault.empty()
    svc = Service(id="s1", name="S")
    acc = Account(id="a1", title="Acc", login="l", password="p")
    svc.accounts.append(acc)
    vault.services.append(svc)

    vault.delete_service(svc)
    assert vault.services == []
    ids = {t.id for t in vault.tombstones}
    assert ids == {"s1", "a1"}, ids


def test_legacy_trash_becomes_tombstones() -> None:
    """Старый формат с корзиной: объекты из неё становятся удалёнными."""
    legacy = {
        "version": 1,
        "services": [{"id": "s1", "name": "Активный", "accounts": []}],
        "trash": [
            {"id": "s2", "kind": "service", "name": "Старый сервис",
             "payload": {}, "deleted_at": 500.0},
            {"id": "a9", "kind": "account", "name": "Старая запись",
             "payload": {}, "deleted_at": 600.0},
        ],
        "tombstones": [],
    }
    vault = Vault.from_dict(legacy)
    assert [s.id for s in vault.services] == ["s1"]
    ids = {t.id for t in vault.tombstones}
    assert ids == {"s2", "a9"}, ids
    # Поля trash в новом формате нет.
    assert "trash" not in vault.to_dict()


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
    # Удалённая запись в экспорт не попадает.
    vault.delete_account(svc, acc)
    assert "Основная" not in build_txt(vault)


def test_export_txt_empty_vault() -> None:
    text = build_txt(Vault.empty())
    assert "Список сервисов пуст" in text
    assert "Сервисов: 0" in text


def test_write_export_creates_dir_and_file() -> None:
    vault = Vault.empty()
    svc = Service(name="Почта")
    svc.accounts.append(Account(title="A", login="u@mail.ru", password="pw"))
    vault.services.append(svc)

    with tempfile.TemporaryDirectory() as tmp:
        path = export.write_export(vault, base_dir=Path(tmp))
        assert path.parent == Path(tmp) / "exports"
        assert path.parent.is_dir()
        assert path.name.startswith("passmanager-")
        assert path.name.endswith(".txt")
        text = path.read_text(encoding="utf-8")
        assert "СЕРВИС: Почта" in text
        assert "u@mail.ru" in text


def test_write_export_repeated_does_not_overwrite() -> None:
    vault = Vault.empty()
    vault.services.append(Service(name="Почта"))
    with tempfile.TemporaryDirectory() as tmp:
        first = export.write_export(vault, base_dir=Path(tmp))
        second = export.write_export(vault, base_dir=Path(tmp))
        assert first != second
        assert first.exists() and second.exists()
        # Оба файла лежат в каталоге exports/.
        assert len(list(export.export_dir(Path(tmp)).glob("*.txt"))) == 2


def test_export_filename_has_timestamp() -> None:
    import re

    name = export.export_filename()
    assert re.fullmatch(r"passmanager-\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.txt",
                        name), name


def test_add_service_appends() -> None:
    vault = Vault.empty()
    vault.add_service(Service(name="B"))
    vault.add_service(Service(name="A"))
    # Порядок хранения — порядок добавления; отображение сортируется отдельно.
    assert [s.name for s in vault.services] == ["B", "A"]


def test_add_account_appends() -> None:
    svc = Service(name="S")
    svc.add_account(Account(title="first"))
    svc.add_account(Account(title="second"))
    assert [a.title for a in svc.accounts] == ["first", "second"]


def test_sort_services_asc_desc() -> None:
    from app import order

    services = [Service(name=n) for n in ("Банан", "яблоко", "Апельсин")]
    assert [s.name for s in order.sort_services(services, descending=False)] \
        == ["Апельсин", "Банан", "яблоко"]
    assert [s.name for s in order.sort_services(services, descending=True)] \
        == ["яблоко", "Банан", "Апельсин"]


def test_sort_accounts_fields_no_password() -> None:
    from app import order

    accounts = []
    for title, login, comment, changed in (
        ("Б", "b@b", "коммент", 200.0),
        ("А", "a@a", "", 100.0),
    ):
        accounts.append(Account(title=title, login=login, comment=comment,
                                password_changed_at=changed))
    got = order.sort_accounts(accounts, "title", descending=False)
    assert [a.title for a in got] == ["А", "Б"]
    got = order.sort_accounts(accounts, "login", descending=True)
    assert [a.login for a in got] == ["b@b", "a@a"]
    got = order.sort_accounts(accounts, "password_changed_at", descending=False)
    assert [a.title for a in got] == ["А", "Б"]
    # Пароль сортировать нельзя.
    try:
        order.sort_accounts(accounts, "password")
    except ValueError:
        pass
    else:
        raise AssertionError("Ожидалась ошибка для сортировки по паролю")


def test_empty_values_sorted_last() -> None:
    from app import order

    accounts = [Account(title=t) for t in ("Б", "", "А")]
    got = order.sort_accounts(accounts, "title", descending=False)
    assert [a.title for a in got] == ["А", "Б", ""]
    # Пустые остаются в конце и при убывании.
    got = order.sort_accounts(accounts, "title", descending=True)
    assert [a.title for a in got] == ["Б", "А", ""]


def test_legacy_order_field_ignored() -> None:
    legacy = {
        "version": 1,
        "services": [
            {"id": "s1", "name": "Первый", "order": 5.0, "order_at": 1.0,
             "accounts": [{"id": "a1", "title": "A", "order": 3.0},
                          {"id": "a2", "title": "B", "order": 1.0}]},
            {"id": "s2", "name": "Второй", "accounts": []},
        ],
    }
    vault = Vault.from_dict(legacy)
    # Поле order из старых файлов игнорируется, порядок из файла сохраняется.
    assert [s.id for s in vault.services] == ["s1", "s2"]
    assert [a.id for a in vault.services[0].accounts] == ["a1", "a2"]
    # Поля order в новых данных нет вовсе.
    assert "order" not in vault.services[0].to_dict()
    assert "order_at" not in vault.services[0].to_dict()
    assert "order" not in vault.services[0].accounts[0].to_dict()


def test_account_list_roundtrips() -> None:
    svc = Service(name="S")
    svc.add_account(Account(title="a"))
    svc.add_account(Account(title="b"))
    restored = Service.from_dict(svc.to_dict())
    assert [a.title for a in restored.accounts] == ["a", "b"]


def test_merge_keeps_edits_content_independent_of_position() -> None:
    # Устройство A отсортировало список, B изменило содержимое сервиса.
    # Сортировка не влияет на данные — слияние сохраняет правку.
    a = Vault.empty()
    a.add_service(Service(id="s1", name="Б"))
    a.add_service(Service(id="s2", name="А"))

    b = Vault.empty()
    b.add_service(Service(id="s1", name="Б-правка", modified_at=9_999_999_999.0))
    b.add_service(Service(id="s2", name="А"))

    merged = merge(a, b)
    assert merged.service("s1").name == "Б-правка"


def test_merge_account_deletion_does_not_resurrect() -> None:
    # A не удалял, B удалил запись — после слияния она удалена.
    a = Vault.empty()
    s = Service(id="s1", name="Почта")
    s.accounts.append(Account(id="a1", title="X", login="u"))
    a.services = [s]

    b = Vault.from_dict(a.to_dict())
    b.delete_account(b.services[0], b.services[0].accounts[0])

    merged = merge(a, b)
    assert merged.all_account_count() == 0
    assert any(t.id == "a1" for t in merged.tombstones)
    # Симметрично: порядок аргументов не важен.
    assert merge(b, a).all_account_count() == 0


def test_merge_service_deletion_does_not_resurrect() -> None:
    # A не удалял, B удалил сервис — после слияния он не «воскресает».
    a = Vault.empty()
    s = Service(id="s1", name="Почта")
    s.accounts.append(Account(id="a1", title="X", login="u"))
    a.services = [s]

    b = Vault.from_dict(a.to_dict())
    b.delete_service(b.services[0])

    merged = merge(a, b)
    assert merged.service("s1") is None
    assert merged.all_account_count() == 0
    ids = {t.id for t in merged.tombstones}
    assert ids == {"s1", "a1"}, ids
    # Симметрично: порядок аргументов не важен.
    assert merge(b, a).service("s1") is None


def test_merge_account_added_on_one_side() -> None:
    a = Vault.empty()
    a.services = [Service(id="s1", name="Почта")]
    b = Vault.from_dict(a.to_dict())
    b.services[0].accounts.append(Account(id="a1", title="X", login="u"))

    merged = merge(a, b)
    assert merged.service("s1").account("a1") is not None
    assert merged.all_account_count() == 1


def test_merge_account_newer_wins() -> None:
    a = Vault.empty()
    s = Service(id="s1", name="Почта")
    s.accounts.append(Account(id="a1", title="X", login="old", modified_at=100.0))
    a.services = [s]

    b = Vault.from_dict(a.to_dict())
    b.services[0].accounts[0].login = "new"
    b.services[0].accounts[0].modified_at = 200.0

    merged = merge(a, b)
    assert merged.service("s1").account("a1").login == "new"
    assert merge(b, a).service("s1").account("a1").login == "new"


def test_account_icon_roundtrips_and_defaults_empty() -> None:
    acc = Account(id="a1", title="X", icon="mail")
    restored = Account.from_dict(acc.to_dict())
    assert restored.icon == "mail"
    # Иконка не обязательна: по умолчанию пусто, старый файл читается.
    assert Account.from_dict({"id": "a2", "title": "Y"}).icon == ""


def test_service_icon_roundtrips_and_defaults_empty() -> None:
    svc = Service(id="s1", name="Почта", icon="wallet")
    restored = Service.from_dict(svc.to_dict())
    assert restored.icon == "wallet"
    assert Service.from_dict({"id": "s2", "name": "Банк"}).icon == ""


def test_icon_change_does_not_add_history() -> None:
    acc = Account(id="a1", title="X", login="u", password="p")
    before = list(acc.history)
    # Смена иконки — не событие журнала.
    acc.icon = "star"
    acc.touch()
    assert acc.history == before


def test_merge_takes_service_icon_from_newer() -> None:
    a = Vault.empty()
    a.services = [Service(id="s1", name="Почта", icon="mail")]
    a.services[0].modified_at = 100.0

    b = Vault.empty()
    b.services = [Service(id="s1", name="Почта", icon="globe")]
    b.services[0].modified_at = 200.0

    merged = merge(a, b)
    assert merged.service("s1").icon == "globe"
    # Симметрично.
    assert merge(b, a).service("s1").icon == "globe"


def test_merge_takes_account_icon_from_newer() -> None:
    a = Vault.empty()
    s = Service(id="s1", name="Почта")
    acc = Account(id="a1", title="X", login="u", password="p", icon="mail")
    acc.modified_at = 100.0
    s.accounts.append(acc)
    a.services = [s]

    b = Vault.from_dict(a.to_dict())
    b.services[0].accounts[0].icon = "star"
    b.services[0].accounts[0].modified_at = 200.0

    merged = merge(a, b)
    assert merged.service("s1").account("a1").icon == "star"


def test_icon_survives_deletion_tombstone() -> None:
    vault = Vault.empty()
    svc = Service(id="s1", name="Почта")
    acc = Account(id="a1", title="X", login="u", password="p", icon="rocket")
    svc.accounts.append(acc)
    vault.services = [svc]

    vault.delete_account(svc, acc)
    assert any(t.id == "a1" for t in vault.tombstones)
    # Слияние не возвращает удалённую запись с иконкой.
    merged = merge(vault, Vault.from_dict(
        {"services": [{"id": "s1", "name": "Почта",
                       "accounts": [acc.to_dict()]}]}))
    assert merged.service("s1").account("a1") is None


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
