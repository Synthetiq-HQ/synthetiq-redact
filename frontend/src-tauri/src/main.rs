// Prevents an extra console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent};

/// Holds the spawned Python backend so we can stop it when the app closes.
struct BackendProcess(Mutex<Option<Child>>);

/// Locate the FastAPI backend directory. Override with SYNTHETIQ_BACKEND_DIR.
fn backend_dir() -> std::path::PathBuf {
    if let Ok(dir) = std::env::var("SYNTHETIQ_BACKEND_DIR") {
        return std::path::PathBuf::from(dir);
    }
    // Run-from-source layout: <repo>/frontend/src-tauri  ->  <repo>/backend
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("backend")
}

/// Pick the Python interpreter. Override with SYNTHETIQ_PYTHON.
fn python_exe() -> String {
    if let Ok(py) = std::env::var("SYNTHETIQ_PYTHON") {
        return py;
    }
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        let candidate = format!("{}\\Programs\\Python\\Python312\\python.exe", local);
        if std::path::Path::new(&candidate).exists() {
            return candidate;
        }
    }
    "python".to_string()
}

/// Start the Synthetiq Redact backend (uvicorn) with the v3 GLM engine enabled.
/// The desktop app uses a private port so it cannot clash with other local tools.
fn spawn_backend() -> Option<Child> {
    let dir = backend_dir();
    if !dir.exists() {
        eprintln!("[synthetiq] backend dir not found: {:?}", dir);
        return None;
    }
    let mut cmd = Command::new(python_exe());
    cmd.current_dir(&dir)
        .args([
            "-m", "uvicorn", "main_v2:app",
            "--host", "127.0.0.1", "--port", "8765",
        ])
        .env("USE_GLM_GEOMETRY_REDACTION", "1")
        .env("ALLOW_OCR_GEOMETRY_FALLBACK", "0")
        .env("OLLAMA_HOST", "http://127.0.0.1:11434")
        .env("GLM_OCR_MODEL", "glm-ocr:latest");

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    match cmd.spawn() {
        Ok(child) => Some(child),
        Err(err) => {
            eprintln!("[synthetiq] failed to start backend: {err}");
            None
        }
    }
}

fn backend_is_listening() -> bool {
    std::net::TcpStream::connect(("127.0.0.1", 8765)).is_ok()
}

fn ollama_exe() -> String {
    if let Ok(p) = std::env::var("OLLAMA_EXE") {
        return p;
    }
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        let candidate = format!("{}\\Programs\\Ollama\\ollama.exe", local);
        if std::path::Path::new(&candidate).exists() {
            return candidate;
        }
    }
    "ollama".to_string()
}

fn ollama_is_listening() -> bool {
    std::net::TcpStream::connect(("127.0.0.1", 11434)).is_ok()
}

/// Ensure the local Ollama server is running — GLM-OCR (Synthetiq Redact v3)
/// depends on it. Left running on exit because it is a shared local service.
fn ensure_ollama() {
    if ollama_is_listening() {
        return;
    }
    let mut cmd = Command::new(ollama_exe());
    cmd.arg("serve");
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    if cmd.spawn().is_ok() {
        for _ in 0..20 {
            if ollama_is_listening() {
                break;
            }
            std::thread::sleep(Duration::from_millis(500));
        }
    }
}

fn wait_for_backend(timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if backend_is_listening() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    false
}

#[cfg(windows)]
fn stop_backend_on_port() {
    let script = r#"
$port = 8765
$conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
  $owner = $conn.OwningProcess
  try {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$owner"
    if ($proc.CommandLine -match "main_v2:app|uvicorn") {
      Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
    }
  } catch {}
}
"#;
    let _ = Command::new("powershell.exe")
        .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])
        .status();
}

#[cfg(not(windows))]
fn stop_backend_on_port() {}

/// Stop the backend if it is running.
fn kill_backend(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<BackendProcess>() {
        if let Ok(mut guard) = state.0.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

#[tauri::command]
fn restart_backend(app: tauri::AppHandle) -> Result<String, String> {
    kill_backend(&app);
    stop_backend_on_port();
    std::thread::sleep(Duration::from_millis(800));

    let child = spawn_backend().ok_or_else(|| "Could not start the local backend.".to_string())?;
    if let Some(state) = app.try_state::<BackendProcess>() {
        let mut guard = state
            .0
            .lock()
            .map_err(|_| "Could not update backend process state.".to_string())?;
        *guard = Some(child);
    }

    if wait_for_backend(Duration::from_secs(25)) {
        Ok("Local backend restarted.".to_string())
    } else {
        Ok("Backend restart requested; it is still starting.".to_string())
    }
}

fn main() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![restart_backend])
        .setup(|app| {
            let launcher_managed = std::env::var("SYNTHETIQ_BACKEND_MANAGED").ok().as_deref() == Some("1");
            ensure_ollama();
            let child = if launcher_managed {
                None
            } else {
                // Hard restart: clear any leftover backend from a previous run (even
                // one that survived a crash or force-quit), then start fresh. This is
                // why opening the app always gets a clean, working backend.
                stop_backend_on_port();
                std::thread::sleep(Duration::from_millis(600));
                spawn_backend()
            };
            if let Some(state) = app.try_state::<BackendProcess>() {
                *state.0.lock().unwrap() = child;
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Synthetiq Redact")
        .run(|app_handle, event| {
            // On close, hard-stop the backend so nothing lingers: kill our spawned
            // child AND anything still holding the port.
            if let RunEvent::Exit = event {
                kill_backend(app_handle);
                stop_backend_on_port();
            }
        });
}
