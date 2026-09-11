#!/usr/bin/env python3
"""Deterministic, redacted CrowdWorks account status/ensure/answer CLI."""
from __future__ import annotations
import argparse, asyncio, inspect, threading
import base64, binascii, html, quopri
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import errno, fcntl
import importlib.util
import json, os, re, shlex, signal, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, TextIO
from urllib.parse import parse_qsl, urlsplit
PLATFORM="crowdworks"; CDP_PORT=9228; CDP_URL=f"http://127.0.0.1:{CDP_PORT}"
PROFILE_DIR=str(Path("~/.local/state/anicca/crowdworks/browser-profile").expanduser()); DEFAULT_STATE_PATH=Path("~/.local/state/anicca/crowdworks/account.json").expanduser()
SESSION_VAULT_DIR=str(Path("~/.local/state/anicca/crowdworks/session-vault").expanduser()); SESSION_VAULT_PORT=str(CDP_PORT); VAULT_DIR=SESSION_VAULT_DIR
LOGIN_URL="https://crowdworks.jp/login"; DASHBOARD_URL="https://crowdworks.jp/dashboard"; PASSWORD_RESET_URL="https://crowdworks.jp/password_reset_requests/new"; PASSWORD_RESET_COMPLETE_URL="https://crowdworks.jp/password_reset_requests/complete"; SIGNUP_URL="https://crowdworks.jp/user/new_email"
SIGNUP_STEP1_URL="https://crowdworks.jp/user/register/step/1"; SIGNUP_STEP2_URL="https://crowdworks.jp/user/register/step/2"; PROFILE_SSOT=Path("~/.config/anicca/job-search/profile.json").expanduser()
KEYCHAIN_SERVICE="ai.anicca.crowdworks.login"; BROWSER_ROOT=Path("~/.cloakbrowser").expanduser(); BROWSER_BINARY=str(BROWSER_ROOT/"Chromium.app/Contents/MacOS/Chromium")
CREDENTIALS_PATH=Path("~/.local/share/anicca/credentials.json").expanduser()
ACCOUNT_RESULT_FIELDS=("ok","platform","authenticated","status","role","request_id","error")
ACCOUNT_INTERFACES={"run_status":"(*, ownership_checker, browser_factory) -> AccountResult","run_ensure":"(*, state_path: Path, allow_signup: bool, ownership_checker, browser_factory, vault_restorer, vault_dumper, credential_loader, notifier, now) -> AccountResult","answer_request":"(*, request_id: str, state_path: Path, input_stream, credential_writer) -> AccountResult","run_signup":"(*, state_path: Path, ownership_checker, browser_factory, mail_reader, profile_reader, password_generator, credential_writer, now) -> AccountResult"}
_MAX=4096; _TERMINAL_TIMEOUT=10.0; _POLL_INTERVAL=.1; _RUNTIME:Any=None; _BROWSER:Any=None
class _Error(RuntimeError):
    def __init__(self,code:str)->None: self.code=code if type(code)is str and re.fullmatch(r"[a-z][a-z0-9_]{1,63}",code) else "account_operation_failed"
@dataclass(frozen=True)
class AccountResult:
    ok:bool; platform:str=PLATFORM; authenticated:bool=False; status:str="error"; role:Optional[str]=None; request_id:Optional[str]=None; error:Optional[str]=None
    def __post_init__(self)->None: object.__setattr__(self,"platform",PLATFORM)
    def to_dict(self)->dict[str,object]:
        out={"ok":bool(self.ok),"platform":PLATFORM,"authenticated":bool(self.authenticated),"status":self.status}
        for key in ("role","request_id","error"):
            if (value:=getattr(self,key)) is not None: out[key]=value
        return out
def _result(status:str,**kw:Any)->AccountResult: return AccountResult(status in {"authenticated","input_ready","signup_step1_complete","signup_complete"},status=status,**kw)
def _state(path:Path)->dict[str,object]:
    try: value=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError,ValueError,TypeError,json.JSONDecodeError): raise _Error("account_state_invalid") from None
    if not isinstance(value,dict): raise _Error("account_state_invalid")
    return value
def _write(path:Path,value:Mapping[str,object])->None:
    allowed={"version","request_id","request_kind","status","notification_receipt","created_at","updated_at"}; payload={k:value[k] for k in allowed if k in value}; fd=temp=None
    try:
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True); fd,temp=tempfile.mkstemp(prefix=f".{path.name}.",dir=str(path.parent)); os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream: fd=None; json.dump(payload,stream,ensure_ascii=False,separators=(",",":")); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp,path); os.chmod(path,0o600)
    except (OSError,TypeError,ValueError): raise _Error("account_state_write_failed") from None
    finally:
        if fd is not None:
            try: os.close(fd)
            except OSError: pass
        if temp:
            try: os.unlink(temp)
            except OSError: pass
def _receipt(value:Any)->Optional[str]:
    if isinstance(value,Mapping):
        for key in ("message_id","messageId","id","receipt"):
            if key in value: value=value[key]; break
    value=str(value).strip() if isinstance(value,(int,str)) and not isinstance(value,bool) else ""
    return value if value and len(value)<=256 and "\n" not in value and "\r" not in value else None
def _request(path:Path,old:Mapping[str,object],status:str,kind:str,notifier:Callable[[str],Any],now:Any)->str:
    old_id=old.get("request_id");rid=old_id if type(old_id)is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",old_id) else f"crowdworks-{uuid.uuid4().hex}";same=old.get("request_kind")==kind and old.get("status")==status;stored=old.get("notification_receipt")
    if same and stored=="pending":return rid
    receipt=_receipt(stored) if same else None
    try:stamp=now() if callable(now) else now
    except Exception:stamp=None
    stamp=stamp.astimezone(timezone.utc).isoformat() if isinstance(stamp,datetime) else stamp if type(stamp)in(str,int,float) and stamp!="" else datetime.now(timezone.utc).isoformat();base={"version":1,"request_id":rid,"request_kind":kind,"status":status,"created_at":old.get("created_at",stamp),"updated_at":stamp}
    if receipt is None:
        _write(path,{**base,"notification_receipt":"pending"})
        try:response=notifier(f"request_kind={kind} request_id={rid}");receipt=_receipt(response) or _receipt(response.get("result") if isinstance(response,Mapping) else None)
        except Exception:raise _Error("notification_failed") from None
        if receipt is None:raise _Error("notification_receipt_missing")
    _write(path,{**base,"notification_receipt":receipt});return rid
@contextmanager
def _account_lock(path:Path):
    lock_path=Path(path).with_name("account.lock");lock_path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);fd=os.open(str(lock_path),os.O_CREAT|os.O_RDWR,0o600)
    try:
        os.fchmod(fd,0o600)
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES,errno.EAGAIN):raise _Error("account_lock_busy") from None
            raise
        yield
    finally:
        try:fcntl.flock(fd,fcntl.LOCK_UN)
        finally:os.close(fd)
def _page(browser:Any)->Any:
    contexts=getattr(browser,"contexts",()); new_page=getattr(contexts[0],"new_page",None) if contexts else None
    if not callable(new_page): raise _Error("browser_page_unavailable")
    try:return new_page()
    except Exception:raise _Error("browser_page_unavailable") from None
def _close(page:Any)->None:
    try:
        if page is not None and callable(getattr(page,"close",None)):page.close()
    except Exception:pass
def _wait(page:Any)->None:
    try:
        if callable(getattr(page,"wait_for_load_state",None)):page.wait_for_load_state(state="domcontentloaded",timeout=10000)
    except Exception:pass
def _auth(page:Any,*,strict:bool=False)->tuple[bool,Optional[str]]:
    try: parsed=urlsplit(getattr(page,"url",""))
    except Exception:
        if strict:raise
        return False,None
    if (parsed.hostname or "").lower() not in {"crowdworks.jp","www.crowdworks.jp"} or parsed.path.rstrip("/")!="/dashboard":return False,None
    try:
        if page.locator('form[action="/login"]').count() or page.locator('input[name="username"]').count():return False,None
        data=json.loads(page.locator("#norman-header-section").get_attribute("data") or "{}"); props=data.get("headerMenuProps",{})
        if not isinstance(props,Mapping) or props.get("isLogin") is not True:return False,None
        role=props.get("userRole"); return True,role.strip()[:128] if type(role)is str and role.strip() else None
    except Exception:
        if strict:raise
        return False,None
def _missing_account(page:Any)->bool:
    try:
        error=page.locator("#login_error")
        return error.count()==1 and error.get_attribute("data-code")=="account_missing" and error.inner_text().strip()=="このメールアドレスはCrowdWorksに登録されていません"
    except Exception:return False
def _password_reset_confirmed(page:Any)->bool:
    try:
        body=page.inner_text("body"); parsed=urlsplit(getattr(page,"url",""))
        if (parsed.hostname or "").lower() not in {"crowdworks.jp","www.crowdworks.jp"} or parsed.path.rstrip("/")!="/password_reset_requests/complete":return False
        return "送信しました" in body and "パスワード再設定" in body and page.locator('form[action="/password_reset_requests"]').count()==0
    except Exception:return False
def _login_terminal(page:Any)->bool:
    if _auth(page)[0] or _missing_account(page):return True
    try:
        body=page.inner_text("body").lower()
        return any(value in body for value in ("incorrect","invalid password","login failed","正しくありません","一致しません","認証コード","verification code","challenge","登録されていません","ログインに失敗"))
    except Exception:return False
def _signup_confirmed(page:Any)->bool:
    try:
        parsed=urlsplit(getattr(page,"url","")); body=page.inner_text("body").lower()
        return (parsed.hostname or "").lower() in {"crowdworks.jp","www.crowdworks.jp"} and parsed.path.rstrip("/")!="/user/new_email" and page.locator('input[name="email_verification_key[email]"]').count()==0 and any(value in body for value in ("送信しました","確認メール","認証メール","verification"))
    except Exception:return False
def _terminal(page:Any,url:str)->bool:
    return _login_terminal(page) if url==LOGIN_URL else _password_reset_confirmed(page) if url==PASSWORD_RESET_URL else _signup_confirmed(page) if url==SIGNUP_URL else True
def _poll_terminal(page:Any,url:str)->bool:
    deadline=time.monotonic()+_TERMINAL_TIMEOUT
    while time.monotonic()<deadline:
        if _terminal(page,url):return True
        time.sleep(_POLL_INTERVAL)
    return _terminal(page,url)
def _submit(page:Any,url:str,field:str,value:str,password:Optional[str]=None)->bool:
    try:page.goto(url)
    except Exception:raise _Error("account_navigation_failed") from None
    _wait(page)
    try:page.locator(field).fill(value); (page.locator('input[name="password"]').fill(password) if password is not None else None)
    except Exception:raise _Error("account_form_unavailable") from None
    if password is not None:
        try:page.locator("#enable_auto_login").check()
        except Exception:raise _Error("account_form_unavailable") from None
    submit_selector={'https://crowdworks.jp/login':'form[action="/login"] button[type="submit"]','https://crowdworks.jp/password_reset_requests/new':'form[action="/password_reset_requests"] input[type="submit"][name="commit"]','https://crowdworks.jp/user/new_email':'form[action="/user/send_email_verification"] button[type="submit"]'}.get(url,'button[type="submit"]')
    try:page.locator(submit_selector).click(no_wait_after=True)
    except Exception:raise _Error("account_submit_failed") from None
    return _poll_terminal(page,url)
_URL_RE=re.compile(r"https?://[^\s<>\"'`]+")
def _decoded(value:str,seen:Optional[set[str]]=None):
    if type(value)is not str:return
    seen=set() if seen is None else seen
    if value in seen:return
    seen.add(value);yield value
    values=[html.unescape(value)]
    if re.search(r"=3D|=0A|=0D|=\r?\n",value,re.IGNORECASE):
        try:values.append(quopri.decodestring(value.encode()).decode("utf-8","replace"))
        except (UnicodeError,ValueError):pass
    compact=value.strip()
    if len(compact)>=8 and re.fullmatch(r"[A-Za-z0-9_-]+",compact):
        try:values.append(base64.urlsafe_b64decode(compact+"="*(-len(compact)%4)).decode("utf-8","replace"))
        except (binascii.Error,UnicodeError,ValueError):pass
    for item in values:
        if type(item)is str:yield from _decoded(item,seen)
def _mail_text(value:Any):
    if isinstance(value,Mapping):
        for key,item in value.items():
            if str(key).lower() in {"id","threadid","historyid","labelids","internaldate","date","from","to","subject"}:continue
            if type(item)is str and str(key).lower() in {"data","body","text","html","snippet","raw","content","value"}:yield from _decoded(item)
            else:yield from _mail_text(item)
    elif isinstance(value,list):
        for item in value:yield from _mail_text(item)
def _verification_link(messages:Any)->str:
    links=set()
    for text in _mail_text(messages):
        for value in _URL_RE.findall(text):
            try:
                value=html.unescape(value).rstrip(".,;:!?)]}>"); parsed=urlsplit(value); pairs=parse_qsl(parsed.query,keep_blank_values=True)
            except (TypeError,ValueError):continue
            if "=3D" in parsed.query.upper():continue
            if parsed.scheme.lower()=="https" and parsed.netloc.lower()=="crowdworks.jp" and parsed.path=="/user/new" and len(pairs)==1 and pairs[0][0]=="key" and pairs[0][1]:links.add(parsed._replace(fragment="").geturl())
    if not links:raise _Error("signup_verification_link_missing")
    if len(links)!=1:raise _Error("signup_verification_link_ambiguous")
    return next(iter(links))
def _json_stdout(text:str)->Any:
    decoder=json.JSONDecoder()
    for index,char in enumerate(text):
        if char not in "[{":continue
        try:return decoder.raw_decode(text[index:])[0]
        except (ValueError,json.JSONDecodeError):continue
    raise _Error("gmail_output_invalid")
def _gog_json(args:Sequence[str])->Any:
    try:proc=subprocess.run(list(args),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=False)
    except Exception:raise _Error("gmail_read_failed") from None
    if getattr(proc,"returncode",1)!=0 or type(getattr(proc,"stdout",None))is not str:raise _Error("gmail_read_failed")
    return _json_stdout(proc.stdout)
def _gog_messages()->list[Mapping[str,object]]:
    value=_gog_json(["gog","gmail","search","from:(crowdworks.jp) newer_than:2d","--max","10","--json"]); rows=value if isinstance(value,list) else next((value.get(key) for key in ("messages","threads","results","data","items") if isinstance(value,Mapping) and isinstance(value.get(key),list)),[]); messages=[]
    for row in rows if isinstance(rows,list) else []:
        if not isinstance(row,Mapping):continue
        if any(key in row for key in ("payload","parts","body","text","html","snippet","raw")):messages.append(row);continue
    if not messages:raise _Error("gmail_content_unavailable" if rows else "gmail_verification_mail_missing")
    return messages
def _profile_username()->str:
    try:value=json.loads(PROFILE_SSOT.read_text(encoding="utf-8")); candidate=value.get("candidate",value) if isinstance(value,Mapping) else {}
    except (OSError,TypeError,ValueError):raise _Error("profile_unavailable") from None
    for key in ("username","crowdworks_username","display_name","preferred_name","name_ja","name"):
        item=candidate.get(key) if isinstance(candidate,Mapping) else None
        if type(item)is str and item.strip():return item.strip()
    raise _Error("profile_username_missing")
def _signup_pending(path:Path,old:Mapping[str,object],now:Any)->dict[str,object]:
    old_id=old.get("request_id"); rid=old_id if type(old_id)is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",old_id) else f"crowdworks-{uuid.uuid4().hex}"; stamp=now() if callable(now) else now; stamp=stamp if type(stamp)in(str,int,float) and stamp!="" else datetime.now(timezone.utc).isoformat(); pending={"version":1,"request_id":rid,"request_kind":"signup_step1","status":"signup_step1_pending","created_at":old.get("created_at",stamp),"updated_at":stamp}; _write(path,pending); return pending
def _signup_route(page:Any,path:str)->bool:
    try:
        parsed=urlsplit(getattr(page,"url",""));
        return parsed.scheme.lower()=="https" and (parsed.hostname or "").lower()=="crowdworks.jp" and parsed.username is None and parsed.password is None and parsed.port in (None,443) and parsed.path==path
    except Exception:return False
def _browser_pages(browser:Any)->list[Any]:
    try:contexts=getattr(browser,"contexts",()); return list(getattr(contexts[0],"pages",())) if contexts else []
    except Exception:return []
def _dashboard_probe(browser:Any)->tuple[Any,bool,Optional[str],bool]:
    for candidate in _browser_pages(browser):
        if _signup_route(candidate,"/dashboard"):
            try:authenticated,role=_auth(candidate,strict=True)
            except Exception:raise _Error("dashboard_probe_failed") from None
            if not authenticated:raise _Error("dashboard_probe_failed")
            if authenticated:return candidate,True,role,False
    page=_page(browser)
    try:
        page.goto(DASHBOARD_URL);_wait(page)
        parsed=urlsplit(getattr(page,"url",""))
        if (parsed.hostname or "").lower() not in {"crowdworks.jp","www.crowdworks.jp"} or parsed.path.rstrip("/") not in {"/dashboard","/login"}:raise RuntimeError
        authenticated,role=_auth(page,strict=True)
        if parsed.path.rstrip("/")=="/dashboard" and not authenticated:raise RuntimeError
    except Exception:raise _Error("dashboard_probe_failed") from None
    return page,authenticated,role,True
def _keychain_password()->str:
    try:value=_credentials().get("password")
    except _Error:raise
    except Exception:raise _Error("credential_unavailable") from None
    if type(value)is not str or not value or len(value)>_MAX or any(not char.isprintable() for char in value):raise _Error("credential_unavailable")
    return value
def _signup_step1(page:Any,link:str,username:str,password:str)->None:
    try:page.goto(link);_wait(page)
    except Exception:raise _Error("signup_navigation_failed") from None
    if not _signup_route(page,"/user/register/step/1"):raise _Error("signup_step1_route_invalid")
    try:
        for selector,value in (("input[name=\"username\"]",username),("input[name=\"password\"]",password),("input[name=\"passwordConfirmation\"]",password)):page.locator(selector).fill(value)
        page.locator('input[type="radio"][value="worker"]').check();page.locator('input[type="radio"][value="individual"]').check();button=page.locator('button:has-text("次に進む")')
        if button.count()!=1 or " ".join(button.inner_text().split())!="次に進む":raise _Error("signup_next_button_missing")
        button.click(no_wait_after=True)
    except _Error:raise
    except Exception:raise _Error("signup_form_unavailable") from None
def _signup_readback(page:Any)->bool:return _signup_route(page,"/user/register/step/2")
def _username(value:Any)->str:
    if type(value)is str and value.strip():return value.strip()
    if isinstance(value,Mapping):
        for key in ("username","crowdworks_username","display_name","preferred_name","name_ja","name"):
            item=value.get(key)
            if type(item)is str and item.strip():return item.strip()
    raise _Error("profile_username_missing")
def _signup_complete_state(path:Path,pending:Mapping[str,object],now:Any)->None:
    stamp=now() if callable(now) else now; stamp=stamp if type(stamp)in(str,int,float) and stamp!="" else datetime.now(timezone.utc).isoformat(); _write(path,{**pending,"status":"signup_step1_complete","updated_at":stamp})
def run_signup(*,state_path:Path,ownership_checker:Callable[[],bool],browser_factory:Callable[[str],Any],mail_reader:Optional[Callable[[],Any]]=None,profile_reader:Optional[Callable[[],Any]]=None,password_generator:Optional[Callable[[],str]]=None,credential_writer:Optional[Callable[[str,str,str],Any]]=None,now:Any=None,gmail_reader:Optional[Callable[[],Any]]=None,username_reader:Optional[Callable[[],Any]]=None,password_factory:Optional[Callable[[],str]]=None,keychain_writer:Optional[Callable[[str,str,str],Any]]=None)->AccountResult:
    path,page,guard,acquired=Path(state_path),None,None,False; mail_reader=mail_reader or gmail_reader or _gog_messages; profile_reader=profile_reader or username_reader or _profile_username; controlled=password_generator is not None or password_factory is not None; password_generator=password_generator or password_factory; credential_writer=credential_writer or keychain_writer or _write_credential; now=now or (lambda:datetime.now(timezone.utc).isoformat()); link=password=username=None; browser=None; _owned=False
    try:
        guard=_account_lock(path);guard.__enter__();acquired=True
        if not bool(ownership_checker()):return _result("browser_ownership_conflict")
        old=_state(path);rid=old.get("request_id") if type(old.get("request_id"))is str else None;browser=browser_factory(CDP_URL)
        if old.get("status")=="signup_step1_pending":
            for candidate in _browser_pages(browser):
                if _signup_route(candidate,"/dashboard"):
                    try:authenticated,role=_auth(candidate,strict=True)
                    except Exception:raise _Error("dashboard_probe_failed") from None
                    if not authenticated:raise _Error("dashboard_probe_failed")
                    if authenticated:return _result("signup_complete",authenticated=True,role=role)
            for candidate in _browser_pages(browser):
                if _signup_readback(candidate):_signup_complete_state(path,old,now);return _result("signup_step1_complete",request_id=rid)
            page,authenticated,role,_owned=_dashboard_probe(browser)
            if authenticated:return _result("signup_complete",authenticated=True,role=role)
            return _result("signup_step1_pending",request_id=rid)
        page,authenticated,role,_owned=_dashboard_probe(browser)
        if authenticated:return _result("signup_complete",authenticated=True,role=role)
        link=_verification_link(mail_reader());username=_username(profile_reader());password=password_generator() if controlled else _keychain_password()
        if type(password)is not str or not password or len(password)>_MAX or any(not char.isprintable() for char in password):raise _Error("password_generation_invalid")
        pending=_signup_pending(path,old,now)
        if controlled:credential_writer(KEYCHAIN_SERVICE,"password",password)
        _signup_step1(page,link,username,password)
        deadline=time.monotonic()+_TERMINAL_TIMEOUT
        while time.monotonic()<deadline and not _signup_readback(page):time.sleep(_POLL_INTERVAL)
        if not _signup_readback(page):_write(path,pending);raise _Error("signup_step1_readback_failed")
        _signup_complete_state(path,pending,now);return _result("signup_step1_complete",request_id=pending.get("request_id"))
    except _Error as error:return _result("error",error=error.code if re.fullmatch(r"[a-z][a-z0-9_]{1,63}",error.code) else "signup_failed")
    except Exception:return _result("error",error="signup_failed")
    finally:
        link=password=username=None
        if acquired:guard.__exit__(*sys.exc_info())
        if page is not None and _owned: _close(page)
def _listener()->Optional[int]:
    try:r=subprocess.run(["/usr/sbin/lsof","-nP",f"-iTCP:{CDP_PORT}","-sTCP:LISTEN","-Fp"],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=False)
    except Exception:return None
    return next((int(line[1:]) for line in getattr(r,"stdout","").splitlines() if line.startswith("p") and line[1:].isdigit()),None)
def _command(pid:int)->str:
    try:r=subprocess.run(["ps","-p",str(pid),"-o","command="],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,check=False);return getattr(r,"stdout","").strip()
    except Exception:return ""
def _command_owns_profile(command:str)->bool:
    try:tokens=shlex.split(command)
    except (TypeError,ValueError):tokens=command.split()
    ports=[];profiles=[];i=0
    while i<len(tokens):
        token=tokens[i]
        if token=="--remote-debugging-port" and i+1<len(tokens):ports.append(tokens[i+1]);i+=1
        elif token.startswith("--remote-debugging-port="):ports.append(token.split("=",1)[1])
        elif token=="--user-data-dir" and i+1<len(tokens):profiles.append(tokens[i+1]);i+=1
        elif token.startswith("--user-data-dir="):profiles.append(token.split("=",1)[1])
        i+=1
    return bool(ports and profiles) and all(port==str(CDP_PORT) for port in ports) and all(profile==PROFILE_DIR for profile in profiles)
def _owned_listener(pid:int,deadline:float)->bool:
    while time.monotonic()<deadline:
        command=_command(pid)
        if command:return _command_owns_profile(command)
        time.sleep(.1)
    return False
def _cdp_alive()->bool:
    try:
        from urllib.request import urlopen
        with urlopen(f"{CDP_URL}/json/version",timeout=5) as response:return response.status==200
    except Exception:return False
def _playwright_alive()->bool:
    try:
        browser=_browser(CDP_URL)
        return bool(browser.is_connected()) and bool(browser.contexts)
    except Exception:return False
def _unlock()->None:
    for name in ("SingletonLock","SingletonCookie","SingletonSocket"):
        try:(Path(PROFILE_DIR)/name).unlink()
        except OSError:pass
def _reap(pid:int)->None:
    try:os.kill(pid,signal.SIGKILL)
    except (OSError,ProcessLookupError,PermissionError):pass
    deadline=time.monotonic()+10
    while time.monotonic()<deadline and _listener() is not None:time.sleep(.1)
    _unlock()
def _owner()->bool:
    pid=_listener()
    # A LISTEN socket does not prove CDP works: a wedged Chromium keeps the port bound while its
    # DevTools endpoint is dead, and a crashed one leaves a SingletonLock that makes every relaunch
    # exit instantly. Both states looked "owned" here, so the loop stayed silently dark from 2026-08-11.
    if pid is not None:
        if not _owned_listener(pid,time.monotonic()+10):return False
        if _cdp_alive() and _playwright_alive():return True
        _reap(pid)
    else:_unlock()
    binary=Path(BROWSER_BINARY)
    if not binary.is_file():
        try:binary=sorted(BROWSER_ROOT.glob("chromium-*/Chromium.app/Contents/MacOS/Chromium"),reverse=True)[0]
        except (OSError,IndexError):raise _Error("browser_binary_unavailable") from None
    try:subprocess.Popen([str(binary),f"--remote-debugging-port={CDP_PORT}",f"--user-data-dir={PROFILE_DIR}","--disable-features=WebAuthentication,WebAuthn","--no-first-run"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    except Exception:raise _Error("browser_launch_failed") from None
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        pid=_listener()
        if pid is not None and _owned_listener(pid,deadline) and _cdp_alive() and _playwright_alive():return True
        time.sleep(.1)
    return False
def _browser(url:str)->Any:
    if url!=CDP_URL:raise _Error("browser_endpoint_invalid")
    global _RUNTIME,_BROWSER
    if _BROWSER is not None and _BROWSER.is_connected():return _BROWSER
    runtime=None
    try:
        from playwright.sync_api import sync_playwright
        runtime=sync_playwright().start();browser=runtime.chromium.connect_over_cdp(CDP_URL,timeout=10_000)
        if not browser.contexts:raise RuntimeError
        _RUNTIME,_BROWSER=runtime,browser;return browser
    except Exception:
        if runtime is not None:
            try:runtime.stop()
            except Exception:pass
        raise _Error("browser_connect_failed") from None
def _restore()->Any:
    try:
        saved=json.loads((Path(SESSION_VAULT_DIR)/"auth-state.json").read_text(encoding="utf-8"));allowed={"name","value","domain","path","expires","httpOnly","secure","sameSite"};cookies=[{key:item[key] for key in allowed if key in item} for item in saved.get("cookies",[]) if isinstance(item,Mapping)]
        if not cookies:raise RuntimeError
        _browser(CDP_URL).contexts[0].add_cookies(cookies);return {"ok":True,"restored":len(cookies)}
    except Exception:raise _Error("vault_restore_failed") from None
def _dump()->Any:
    try:
        path=Path(SESSION_VAULT_DIR)/"auth-state.json";cookies=_browser(CDP_URL).contexts[0].cookies()
        if not cookies:raise RuntimeError
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);fd,temp=tempfile.mkstemp(prefix=".auth-state.",dir=path.parent);os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump({"ts":int(time.time()),"cookies":cookies},stream,separators=(",",":"));stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path);os.chmod(path,0o600);return {"ok":True,"cookies":len(cookies)}
    except Exception:raise _Error("vault_dump_failed") from None
def _dump_checked(call:Callable[[],Any])->Any:
    try:value=_resolve(call())
    except _Error:raise _Error("vault_dump_failed") from None
    except Exception:raise _Error("vault_dump_failed") from None
    if value is False or isinstance(value,Mapping) and value.get("ok") is not True:raise _Error("vault_dump_failed")
    return value
def _resolve(value:Any)->Any:
    if not inspect.isawaitable(value):return value
    try:asyncio.get_running_loop()
    except RuntimeError:return asyncio.run(value)
    result=[];errors=[]
    def worker()->None:
        try:result.append(asyncio.run(value))
        except BaseException as error:errors.append(error)
    thread=threading.Thread(target=worker);thread.start();thread.join()
    if errors:raise errors[0]
    return result[0] if result else None
def _credentials()->Mapping[str,str]:
    try:
        payload=json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8")); items=payload.get("credentials",[]) if isinstance(payload,Mapping) else []
        item=next((value for value in items if isinstance(value,Mapping) and str(value.get("service","")).lower() in {"crowdworks","ai.anicca.crowdworks.login"}),None)
        email=item.get("email") or item.get("username") if isinstance(item,Mapping) else None;password=item.get("password") if isinstance(item,Mapping) else None
    except Exception:email=password=None
    if type(email)is not str or not email or type(password)is not str or not password:raise _Error("credential_unavailable")
    return {"email":email,"password":password}
def _write_credential(service:str,account:str,value:str)->None:
    try:
        import keyring;keyring.set_password(service,account,value)
    except Exception:raise _Error("credential_write_failed") from None
ROOT=Path(__file__).resolve().parents[4]
DELIVERY_PATH=ROOT/"skills"/"_shared"/"marketplace-core"/"scripts"/"telegram_delivery.py"
CHAT_CONFIG=Path("~/.config/anicca/crowdworks/telegram.env").expanduser()
def _report_chat()->str:
    """Where the credential request goes; never a repository literal, so a clone cannot message a stranger."""
    for key in ("CROWDWORKS_REPORT_CHAT","GIG_REPORT_CHAT"):
        value=os.environ.get(key,"").strip()
        if value:return value
    try:lines=CHAT_CONFIG.read_text(encoding="utf-8").splitlines()
    except OSError:return ""
    for raw in lines:
        name,_,value=raw.partition("=")
        if name.strip() in ("CROWDWORKS_REPORT_CHAT","GIG_REPORT_CHAT"):return value.strip()
    return ""
def _delivery():
    """The sender Lancers and the CrowdWorks reporter already share. Never a CLI: launchd gives a
    job no PATH, so shelling out to a Homebrew binary fails as process_not_started and this lane
    stops asking for the credentials it is blocked on -- silently, while exiting 0."""
    name="crowdworks_account_delivery"
    if name in sys.modules:return sys.modules[name]
    spec=importlib.util.spec_from_file_location(name,DELIVERY_PATH)
    if spec is None or spec.loader is None:raise _Error("notification_failed")
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module);return module
def _notify(message:str)->Mapping[str,str]:
    try:
        target=_report_chat()
        if not target:raise RuntimeError
        result=_delivery().send_via_shared_client(message,chat_id=target)
        receipt=_receipt(getattr(result,"provider_id",None))
        if receipt is None:raise RuntimeError
        return {"message_id":receipt}
    except Exception:raise _Error("notification_failed") from None
def run_status(*,ownership_checker:Callable[[],bool],browser_factory:Callable[[str],Any])->AccountResult:
    page=None
    try:
        if not bool(ownership_checker()):return _result("browser_ownership_conflict")
        page=_page(browser_factory(CDP_URL));page.goto(DASHBOARD_URL);_wait(page);authenticated,role=_auth(page);return _result("authenticated" if authenticated else "logged_out",authenticated=authenticated,role=role)
    except _Error as error:return _result("error",error=error.code if re.fullmatch(r"[a-z][a-z0-9_]{1,63}",error.code) else "account_status_failed")
    except Exception:return _result("error",error="account_status_failed")
    finally:_close(page)
def run_ensure(*,state_path:Path,allow_signup:bool,ownership_checker:Callable[[],bool],browser_factory:Callable[[str],Any],vault_restorer:Callable[[],Any],vault_dumper:Callable[[],Any],credential_loader:Callable[[],Any],notifier:Callable[[str],Any],now:Any)->AccountResult:
    path,page,keep,guard,acquired=Path(state_path),None,False,None,False
    try:
        guard=_account_lock(path);guard.__enter__();acquired=True
        if not bool(ownership_checker()):return _result("browser_ownership_conflict")
        old=_state(path);_resolve(vault_restorer());page=_page(browser_factory(CDP_URL));page.goto(DASHBOARD_URL);_wait(page);authenticated,role=_auth(page)
        if authenticated:_dump_checked(vault_dumper);return _result("authenticated",authenticated=True,role=role)
        item=email=password=None
        try:
            item=credential_loader();email=item.get("email") if isinstance(item,Mapping) else item[0] if isinstance(item,(tuple,list)) and len(item)==2 else getattr(item,"email",None);password=item.get("password") if isinstance(item,Mapping) else item[1] if isinstance(item,(tuple,list)) and len(item)==2 else getattr(item,"password",None)
            if type(email)is not str or not email or type(password)is not str or not password or len(email)>_MAX or len(password)>_MAX or any(not char.isprintable() for char in email+password):raise _Error("credential_unavailable")
        except Exception as error:
            code=error.code if isinstance(error,_Error) else getattr(error,"code",None) if type(getattr(error,"code",None)) is str else "credential_unavailable"
            if code in {"credential_unavailable","credential_invalid","credential_backend_error"}:return _result("input_required",request_id=_request(path,old,"input_required","credentials",notifier,now))
            raise _Error(code) from None
        try:
            if not _submit(page,LOGIN_URL,'input[name="username"]',email,password):raise _Error("account_terminal_timeout")
            authenticated,role=_auth(page)
            if authenticated:_dump_checked(vault_dumper);return _result("authenticated",authenticated=True,role=role)
            text=page.inner_text("body")
            if _missing_account(page):
                if not allow_signup:return _result("account_missing",error="account_missing")
                if not _submit(page,SIGNUP_URL,'input[name="email_verification_key[email]"]',email):raise _Error("signup_confirmation_missing")
                keep=True;return _result("signup_required",request_id=_request(path,old,"signup_required","signup",notifier,now))
            if any(value.lower() in text.lower() for value in ("incorrect","invalid password","login failed","正しくありません","一致しません")):
                return _result("credential_invalid",error="credential_invalid")
            keep=True;return _result("input_required",request_id=_request(path,old,"input_required","verification",notifier,now))
        finally:
            isinstance(item,dict) and item.update(email=None,password=None);email=password=None
    except _Error as error:return _result("error",error=error.code if re.fullmatch(r"[a-z][a-z0-9_]{1,63}",error.code) else "account_ensure_failed")
    except Exception:return _result("error",error="account_ensure_failed")
    finally:
        if acquired:guard.__exit__(*sys.exc_info())
        if not keep:_close(page)
def _lines(stream:Any)->tuple[str,str]:
    values=[]
    try:
        for _ in range(2):
            line=stream.readline(_MAX+2)
            if type(line)is not str or not line.endswith("\n"):raise _Error("credential_input_invalid")
            value=line[:-1].rstrip("\r")
            if not value or len(value)>_MAX or any(not char.isprintable() for char in value):raise _Error("credential_input_invalid")
            values.append(value)
        if callable(getattr(stream,"read",None)) and stream.read(1) not in ("",None):raise _Error("credential_input_invalid")
        return values[0],values[1]
    finally:values.clear()
def answer_request(*,request_id:str,state_path:Path,input_stream:Any,credential_writer:Callable[[str,str,str],Any])->AccountResult:
    path,guard,acquired=Path(state_path),None,False
    try:
        guard=_account_lock(path);guard.__enter__();acquired=True
        if type(request_id)is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",request_id):return _result("input_invalid",error="credential_input_invalid")
        state=_state(path);stored=state.get("request_id")
        if stored!=request_id or state.get("status") not in {"input_required","ready","password_reset_required","signup_required"}:return _result("input_invalid",request_id=request_id,error="request_invalid")
        email,password=_lines(input_stream);credential_writer(KEYCHAIN_SERVICE,"email",email);credential_writer(KEYCHAIN_SERVICE,"password",password);kind=state.get("request_kind","credentials");kind=kind if type(kind)is str and re.fullmatch(r"[a-z][a-z0-9_]{1,63}",kind) else "credentials";payload={"version":1,"request_id":request_id,"request_kind":kind,"status":"ready","created_at":state.get("created_at",datetime.now(timezone.utc).isoformat()),"updated_at":datetime.now(timezone.utc).isoformat()};receipt=_receipt(state.get("notification_receipt"))
        if receipt is not None:payload["notification_receipt"]=receipt
        _write(path,payload);return _result("input_ready",request_id=request_id)
    except _Error as error:return _result("error",error=error.code if re.fullmatch(r"[a-z][a-z0-9_]{1,63}",error.code) else "credential_input_invalid")
    except Exception:return _result("error",error="credential_input_invalid")
    finally:
        if acquired:guard.__exit__(*sys.exc_info())
        email=password=None
def _parser()->argparse.ArgumentParser:
    parser=argparse.ArgumentParser(allow_abbrev=False);commands=parser.add_subparsers(dest="command",required=True);status=commands.add_parser("status",allow_abbrev=False);status.add_argument("--json",action="store_true",required=True);ensure=commands.add_parser("ensure",allow_abbrev=False);ensure.add_argument("--json",action="store_true",required=True);ensure.add_argument("--allow-signup",action="store_true");answer=commands.add_parser("answer",allow_abbrev=False);answer.add_argument("--request-id",required=True);answer.add_argument("--stdin",action="store_true",required=True);signup=commands.add_parser("signup",allow_abbrev=False);signup.add_argument("--json",action="store_true",required=True)
    for command in (status,ensure,answer,signup):command.add_argument("--state-path",default=str(DEFAULT_STATE_PATH))
    return parser
def main(argv:Optional[Sequence[str]]=None,*,ownership_checker:Optional[Callable[[],bool]]=None,browser_factory:Optional[Callable[[str],Any]]=None,vault_restorer:Optional[Callable[[],Any]]=None,vault_dumper:Optional[Callable[[],Any]]=None,credential_loader:Optional[Callable[[],Any]]=None,credential_writer:Optional[Callable[[str,str,str],Any]]=None,notifier:Optional[Callable[[str],Any]]=None,now:Any=None,input_stream:Optional[Any]=None,stdout:Optional[TextIO]=None,stderr:Optional[TextIO]=None,mail_reader:Optional[Callable[[],Any]]=None,profile_reader:Optional[Callable[[],Any]]=None,password_generator:Optional[Callable[[],str]]=None)->int:
    output,errors=sys.stdout if stdout is None else stdout,sys.stderr if stderr is None else stderr
    try:
        args=_parser().parse_args(argv)
        if args.command=="status":result=run_status(ownership_checker=_owner if ownership_checker is None else ownership_checker,browser_factory=_browser if browser_factory is None else browser_factory)
        elif args.command=="ensure":result=run_ensure(state_path=Path(args.state_path),allow_signup=bool(args.allow_signup),ownership_checker=_owner if ownership_checker is None else ownership_checker,browser_factory=_browser if browser_factory is None else browser_factory,vault_restorer=_restore if vault_restorer is None else vault_restorer,vault_dumper=_dump if vault_dumper is None else vault_dumper,credential_loader=_credentials if credential_loader is None else credential_loader,notifier=_notify if notifier is None else notifier,now=(lambda:datetime.now(timezone.utc).isoformat()) if now is None else now)
        elif args.command=="answer":result=answer_request(request_id=args.request_id,state_path=Path(args.state_path),input_stream=sys.stdin if input_stream is None else input_stream,credential_writer=_write_credential if credential_writer is None else credential_writer)
        else:result=run_signup(state_path=Path(args.state_path),ownership_checker=_owner if ownership_checker is None else ownership_checker,browser_factory=_browser if browser_factory is None else browser_factory,mail_reader=mail_reader,profile_reader=profile_reader,password_generator=password_generator,credential_writer=credential_writer,now=now)
    except SystemExit as error:return int(error.code) if isinstance(error.code,int) else 2
    except Exception:result=_result("error",error="account_operation_failed")
    try:output.write(json.dumps(result.to_dict(),ensure_ascii=False,separators=(",",":"))+"\n");output.flush()
    except Exception:
        try:errors.write("output_failed\n");errors.flush()
        except Exception:pass
        return 5
    return 0 if result.ok else 1
__all__=["ACCOUNT_INTERFACES","ACCOUNT_RESULT_FIELDS","AccountResult","CDP_PORT","CDP_URL","DASHBOARD_URL","DEFAULT_STATE_PATH","KEYCHAIN_SERVICE","LOGIN_URL","PASSWORD_RESET_COMPLETE_URL","PASSWORD_RESET_URL","PROFILE_DIR","PROFILE_SSOT","SESSION_VAULT_DIR","SESSION_VAULT_PORT","SIGNUP_STEP1_URL","SIGNUP_STEP2_URL","SIGNUP_URL","VAULT_DIR","answer_request","main","run_ensure","run_signup","run_status"]
if __name__=="__main__":raise SystemExit(main())
