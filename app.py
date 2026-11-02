import json
import os
import uuid
from importlib.metadata import PackageNotFoundError, version

import streamlit as st
import yaml

DB_DIR = "/app/data"
BLOCKY_CONFIG_DIR = "/app/blocky_config"
DB_PATH = os.path.join(DB_DIR, "app_db.json")
GENERATED_YAML_NAME = os.getenv("GENERATED_YAML_NAME", "20_parental_generated.yml")
GENERATED_YAML_PATH = os.path.join(BLOCKY_CONFIG_DIR, GENERATED_YAML_NAME)

try:
    APP_VERSION = version("blocky-blocking-editor")
except PackageNotFoundError:
    APP_VERSION = "development"

st.set_page_config(page_title="Blocky Parental UI", page_icon="🛡️", layout="wide")


def save_db(data):
    os.makedirs(DB_DIR, exist_ok=True)
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def load_db():
    os.makedirs(DB_DIR, exist_ok=True)
    if not os.path.exists(DB_PATH):
        save_db({"lists": {}, "schedules": [], "clients": []})
    with open(DB_PATH) as f:
        data = json.load(f)

    # Upgrade old databases with domains stored as strings, preserving every entry.
    migrated = False
    for list_data in data.get("lists", {}).values():
        new_domains = []
        for entry in list_data.get("domains", []):
            if isinstance(entry, str):
                entry = {"id": uuid.uuid4().hex, "value": entry, "enabled": True}
                migrated = True
            elif "id" not in entry:
                entry["id"] = uuid.uuid4().hex
                migrated = True
            if "type" not in entry:
                entry["type"] = "domain"
                migrated = True
            if "enabled" not in entry:
                entry["enabled"] = True
                migrated = True
            new_domains.append(entry)
        list_data["domains"] = new_domains
    if migrated:
        save_db(data)
    return data


db = load_db()


def persist():
    """Persist all widget edits immediately, including multiselect changes."""
    save_db(db)


class LiteralString(str):
    """Render an inline Blocky source as a YAML literal block."""


def represent_literal(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")


yaml.SafeDumper.add_representer(LiteralString, represent_literal)


def build_blocky_config(data):
    blocking = {
        "denylists": {}, "allowlists": {}, "schedules": {},
        "listSchedules": {}, "clientGroupsBlock": {},
    }
    for name, list_data in data["lists"].items():
        inline = []
        sources = []
        for entry in list_data["domains"]:
            if isinstance(entry, str):
                entry = {"type": "domain", "value": entry, "enabled": True}
            value = entry.get("value", "").strip()
            if not entry.get("enabled", True) or not value:
                continue
            if entry.get("type", "domain") == "domain":
                inline.append(value)
            elif entry["type"] in ("url", "file"):
                if "\n" in value:
                    raise ValueError(f"Source path/URL in {name} cannot contain newlines")
                sources.append(value)
            else:
                raise ValueError(f"Unknown source type: {entry['type']}")
        if inline:
            sources.insert(0, LiteralString("\n".join(inline) + "\n"))
        target = "denylists" if list_data["type"] == "denylist" else "allowlists"
        blocking[target][name] = sources

    for sch in data["schedules"]:
        rule = {"weekdays": sch["weekdays"]}
        if sch.get("start") and sch.get("end"):
            rule.update(start=sch["start"], end=sch["end"])
        elif sch.get("start") or sch.get("end"):
            raise ValueError(f"Schedule {sch['name']} requires both start and end")
        blocking["schedules"][sch["name"]] = rule
        for name in sch.get("target_lists", []):
            if name in data["lists"]:
                names = blocking["listSchedules"].setdefault(name, [])
                if sch["name"] not in names:
                    names.append(sch["name"])

    for client in data["clients"]:
        blocking["clientGroupsBlock"][client["identifier"]] = [
            name for name in client["assigned_lists"] if name in data["lists"]
        ]
    return {"blocking": blocking}


def compile_blocky_yaml():
    output = build_blocky_config(db)
    os.makedirs(os.path.dirname(GENERATED_YAML_PATH), exist_ok=True)
    with open(GENERATED_YAML_PATH, "w") as f:
        yaml.safe_dump(output, f, default_flow_style=False, sort_keys=False,
                       allow_unicode=True)


st.title("🛡️ Blocky DNS Parental Control")
st.caption(f"Version {APP_VERSION}")
st.write("Manage blocklists, allowlists, timetables, and devices dynamically.")
tab1, tab2, tab3 = st.tabs(["🌐 Lists & Categories", "⏱️ Schedules", "📱 Devices"])

with tab1:
    st.header("Web Filtering Lists")
    if not db["lists"]:
        st.info("No lists created yet. Add one below to start filtering.")

    for list_name in list(db["lists"]):
        list_data = db["lists"][list_name]
        badge = "🔴 DENY" if list_data["type"] == "denylist" else "🟢 ALLOW"
        with st.expander(f"{badge} | List: {list_name.upper()}", expanded=True):
            st.caption("Each domain is editable individually; active domains are compiled into one inline source.")
            for entry in list(list_data["domains"]):
                entry_id = entry["id"]
                kind = entry.get("type", "domain")
                col_enabled, col_type, col_value, col_delete = st.columns(
                    [0.6, 2, 9, 0.8], gap="small", vertical_alignment="center"
                )
                with col_enabled:
                    entry["enabled"] = st.checkbox(
                        "Enabled", value=entry["enabled"], key=f"enabled_{entry_id}",
                        label_visibility="collapsed"
                    )
                with col_type:
                    entry["type"] = st.selectbox(
                        "Source type", ["domain", "url", "file"],
                        index=["domain", "url", "file"].index(kind),
                        key=f"type_{entry_id}", label_visibility="collapsed"
                    )
                with col_value:
                    entry["value"] = st.text_input(
                        "Value", value=entry["value"], key=f"domain_{entry_id}",
                        label_visibility="collapsed",
                        placeholder={"domain": "example.com", "url": "https://example.org/list.txt",
                                     "file": "/path/in/blocky/container/list.txt"}[entry["type"]]
                    )
                with col_delete:
                    if st.button("✕", key=f"remove_{entry_id}", help="Delete source permanently"):
                        list_data["domains"] = [e for e in list_data["domains"] if e["id"] != entry_id]
                        save_db(db)
                        st.rerun()

            if st.button("➕ Add source", key=f"add_domain_{list_name}"):
                list_data["domains"].append({
                    "id": uuid.uuid4().hex, "type": "domain", "value": "", "enabled": True
                })
                save_db(db)
                st.rerun()
            if st.button(f"Delete List '{list_name}'", key=f"del_{list_name}"):
                del db["lists"][list_name]
                for sch in db["schedules"]:
                    sch["target_lists"] = [n for n in sch["target_lists"] if n != list_name]
                for cl in db["clients"]:
                    cl["assigned_lists"] = [n for n in cl["assigned_lists"] if n != list_name]
                save_db(db)
                st.rerun()

    st.subheader("Create New List")
    col1, col2 = st.columns([2, 1])
    with col1:
        new_list_name = st.text_input("List Name (e.g. school, social, ads)").lower().strip()
    with col2:
        new_list_type = st.selectbox("List Type", ["denylist", "allowlist"])
    if st.button("Add List") and new_list_name and new_list_name not in db["lists"]:
        db["lists"][new_list_name] = {"type": new_list_type, "domains": []}
        save_db(db)
        st.rerun()

with tab2:
    st.header("Timetables & Rules")
    if not db["schedules"]:
        st.info("No time schedules configured. Active lists will apply 24/7.")

    for i, sch in enumerate(db["schedules"]):
        with st.container(border=True):
            st.subheader(f"⏱️ Schedule: {sch['name']}")
            col1, col2 = st.columns(2)
            with col1:
                sch["start"] = st.text_input("Start Time (HH:MM)", value=sch["start"], key=f"start_{i}")
                sch["end"] = st.text_input("End Time (HH:MM)", value=sch["end"], key=f"end_{i}")
            with col2:
                days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                sch["weekdays"] = st.multiselect("Active Days", days, default=sch["weekdays"], key=f"days_{i}")
            sch["target_lists"] = st.multiselect(
                "Apply this schedule restriction to which lists?",
                list(db["lists"]), default=sch["target_lists"], key=f"sch_lists_{i}"
            )
            if st.button("Delete Schedule", key=f"del_sch_{i}"):
                db["schedules"].pop(i)
                save_db(db)
                st.rerun()

    if st.button("➕ Create New Schedule Rule"):
        used_names = {sch["name"] for sch in db["schedules"]}
        number = 1
        while f"schedule_{number}" in used_names:
            number += 1
        db["schedules"].append({
            "name": f"schedule_{number}", "weekdays": ["mon", "tue", "wed", "thu", "fri"],
            "start": "08:00", "end": "14:00", "target_lists": []
        })
        save_db(db)
        st.rerun()

with tab3:
    st.header("Managed Devices")
    if not db["clients"]:
        st.info("No devices registered. Default policies will apply in Blocky.")

    for i, cl in enumerate(db["clients"]):
        with st.container(border=True):
            col1, col2 = st.columns(2)
            with col1:
                cl["alias"] = st.text_input("Friendly Alias", value=cl["alias"], key=f"alias_{i}")
                cl["identifier"] = st.text_input("Technical Identifier (IP, CIDR or Hostname*)", value=cl["identifier"], key=f"id_{i}")
            with col2:
                cl["assigned_lists"] = st.multiselect(
                    "Assign filtering lists to this device", list(db["lists"]),
                    default=cl["assigned_lists"], key=f"cl_lists_{i}"
                )
            if st.button("Remove Device", key=f"del_cl_{i}"):
                db["clients"].pop(i)
                save_db(db)
                st.rerun()

    if st.button("➕ Link New Device"):
        db["clients"].append({
            "alias": "New Device", "identifier": "192.168.1.X", "assigned_lists": []
        })
        save_db(db)
        st.rerun()

# Persist changes from every widget on each rerun (including schedules and clients).
save_db(db)
st.divider()
if st.button("💾 DEPLOY CONFIGURATION TO BLOCKY", type="primary", use_container_width=True):
    try:
        compile_blocky_yaml()
    except (ValueError, OSError) as exc:
        st.error(f"Cannot generate configuration: {exc}")
    else:
        st.success("Configuration compiled successfully! Watcher container will trigger Blocky reload.")
