// Prevents an extra console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
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

fn main() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            let launcher_managed = std::env::var("SYNTHETIQ_BACKEND_MANAGED").ok().as_deref() == Some("1");
            let child = if launcher_managed || backend_is_listening() {
                None
            } else {
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
            // When the app fully exits, make sure the backend goes with it.
            if let RunEvent::Exit = event {
                kill_backend(app_handle);
            }
        });
}
