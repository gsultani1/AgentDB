#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{
    AppHandle, Manager, RunEvent,
    menu::{MenuBuilder, MenuItemBuilder},
    tray::TrayIconBuilder,
};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

fn resolve_data_dir() -> PathBuf {
    // Use %APPDATA%/AgentDB (or equivalent) for persistent data
    let base = dirs::data_dir()
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    let dir = base.join("AgentDB");
    let _ = std::fs::create_dir_all(&dir);
    dir
}

struct SidecarState {
    process: Option<Child>,
    data_dir: PathBuf,
    port: u16,
}

impl SidecarState {
    fn new() -> Self {
        let data_dir = resolve_data_dir();
        Self {
            process: None,
            data_dir,
            port: 8420,
        }
    }

    fn db_path(&self) -> PathBuf {
        self.data_dir.join("agentdb.db")
    }

    fn spawn(&mut self) -> Result<(), String> {
        if let Some(ref mut child) = self.process {
            match child.try_wait() {
                Ok(Some(_)) => { self.process = None; }
                Ok(None) => { return Ok(()); }
                Err(_) => { self.process = None; }
            }
        }

        let python = if cfg!(target_os = "windows") {
            "python"
        } else {
            "python3"
        };

        let db = self.db_path();
        let db_str = db.to_string_lossy().to_string();

        // Auto-initialize database if it doesn't exist
        if !db.exists() {
            let mut cmd = Command::new(python);
            cmd.args(["-m", "agentdb.cli", "--db", &db_str, "init"])
                .current_dir(&self.data_dir)
                .stdout(Stdio::null())
                .stderr(Stdio::null());
            #[cfg(target_os = "windows")]
            cmd.creation_flags(CREATE_NO_WINDOW);
            let _ = cmd.status();
        }

        let log_path = self.data_dir.join("sidecar.log");
        let log_file = std::fs::File::create(&log_path).ok();
        let stderr_out = log_file.map(Stdio::from).unwrap_or_else(Stdio::null);

        let mut cmd = Command::new(python);
        cmd.args([
                "-m", "agentdb.cli",
                "--db", &db_str,
                "serve",
                "--port", &self.port.to_string(),
            ])
            .current_dir(&self.data_dir)
            .stdout(Stdio::null())
            .stderr(stderr_out);
        #[cfg(target_os = "windows")]
        cmd.creation_flags(CREATE_NO_WINDOW);
        let child = cmd.spawn()
            .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;

        self.process = Some(child);
        Ok(())
    }

    fn kill(&mut self) {
        if let Some(ref mut child) = self.process {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.process = None;
    }

    fn is_alive(&mut self) -> bool {
        if let Some(ref mut child) = self.process {
            match child.try_wait() {
                Ok(Some(_)) => {
                    self.process = None;
                    false
                }
                Ok(None) => true,
                Err(_) => false,
            }
        } else {
            false
        }
    }
}

fn health_check(port: u16) -> bool {
    let url = format!("http://127.0.0.1:{}/api/agent/health", port);
    match reqwest::blocking::get(&url) {
        Ok(resp) => resp.status().is_success(),
        Err(_) => false,
    }
}

fn start_health_monitor(sidecar: Arc<Mutex<SidecarState>>, _app_handle: AppHandle) {
    thread::spawn(move || {
        // Give sidecar time to start
        thread::sleep(Duration::from_secs(3));

        loop {
            thread::sleep(Duration::from_secs(5));

            let mut state = sidecar.lock().unwrap();
            let port = state.port;

            if !state.is_alive() {
                println!("[AgentDB] Sidecar process died. Restarting...");
                if let Err(e) = state.spawn() {
                    eprintln!("[AgentDB] Failed to restart sidecar: {}", e);
                }
                drop(state);
                thread::sleep(Duration::from_secs(3));
                continue;
            }
            drop(state);

            if !health_check(port) {
                println!("[AgentDB] Health check failed. Restarting sidecar...");
                let mut state = sidecar.lock().unwrap();
                state.kill();
                if let Err(e) = state.spawn() {
                    eprintln!("[AgentDB] Failed to restart sidecar: {}", e);
                }
            }
        }
    });
}

fn main() {
    let sidecar = Arc::new(Mutex::new(SidecarState::new()));
    let sidecar_clone = sidecar.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_process::init())
        .setup(move |app| {
            // Spawn the Python sidecar
            {
                let mut state = sidecar_clone.lock().unwrap();
                if let Err(e) = state.spawn() {
                    eprintln!("[AgentDB] Initial sidecar spawn failed: {}", e);
                }
            }

            // Start health monitoring
            let monitor_sidecar = sidecar_clone.clone();
            let monitor_handle = app.handle().clone();
            start_health_monitor(monitor_sidecar, monitor_handle);

            // Build system tray
            let show = MenuItemBuilder::with_id("show", "Show AgentDB").build(app)?;
            let health = MenuItemBuilder::with_id("health", "Check Health").build(app)?;
            let restart = MenuItemBuilder::with_id("restart", "Restart Sidecar").build(app)?;
            let quit = MenuItemBuilder::with_id("quit", "Quit").build(app)?;

            let menu = MenuBuilder::new(app)
                .item(&show)
                .separator()
                .item(&health)
                .item(&restart)
                .separator()
                .item(&quit)
                .build()?;

            let tray_sidecar = sidecar_clone.clone();
            let _tray = TrayIconBuilder::new()
                .tooltip("AgentDB")
                .menu(&menu)
                .on_menu_event(move |app, event| {
                    match event.id().as_ref() {
                        "show" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                        "health" => {
                            let state = tray_sidecar.lock().unwrap();
                            let ok = health_check(state.port);
                            println!("[AgentDB] Health: {}", if ok { "OK" } else { "FAILED" });
                        }
                        "restart" => {
                            let mut state = tray_sidecar.lock().unwrap();
                            state.kill();
                            if let Err(e) = state.spawn() {
                                eprintln!("[AgentDB] Restart failed: {}", e);
                            }
                        }
                        "quit" => {
                            let mut state = tray_sidecar.lock().unwrap();
                            state.kill();
                            std::process::exit(0);
                        }
                        _ => {}
                    }
                })
                .build(app)?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error building AgentDB")
        .run(move |_app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                println!("[AgentDB] Shutting down sidecar...");
                let mut state = sidecar.lock().unwrap();
                state.kill();
            }
        });
}
