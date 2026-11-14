// Krazow release kit: the Windows app. It serves the web app's own files on this computer and opens them in an
// Edge (or Chrome) app window. The app's data is kept in that window's own profile under
// %LOCALAPPDATA%\krazow\<id>, separate from your normal browser.
package main

import (
	"embed"
	"fmt"
	"io/fs"
	"mime"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"krazow/webapp/internal/win"
)

//go:embed web
var webFiles embed.FS

var version = "dev" // set at build time

const marker = "/__krazow-app"

func main() {
	for _, a := range os.Args[1:] {
		switch strings.ToLower(a) {
		case "--uninstall", "/uninstall":
			uninstall()
			return
		case "--version":
			fmt.Println(version)
			return
		}
	}
	addr := fmt.Sprintf("127.0.0.1:%d", win.Port)
	url := "http://" + addr + "/"

	ln, err := net.Listen("tcp", addr)
	if err != nil {
		if alreadyOurs(addr) { // already running: just open another window on it
			if b := browser(); b != "" {
				_ = launch(b, url).Start()
			} else {
				openDefault(url)
			}
			return
		}
		win.Fail(win.AppName+" can't start",
			fmt.Sprintf("Another program is using port %d on this computer, which %s needs. Close that program and try again.", win.Port, win.AppName))
	}
	go func() { _ = http.Serve(ln, handler()) }()

	b := browser()
	if b == "" {
		openDefault(url)
		time.Sleep(12 * time.Hour)
		return
	}
	cmd := launch(b, url)
	if err := cmd.Start(); err != nil {
		win.Fail(win.AppName+" can't open its window", err.Error())
	}
	_ = cmd.Wait() // ends when the last app window closes
	time.Sleep(3 * time.Second)
}

func handler() http.Handler {
	sub, _ := fs.Sub(webFiles, "web")
	_ = mime.AddExtensionType(".webmanifest", "application/manifest+json")
	_ = mime.AddExtensionType(".js", "text/javascript; charset=utf-8")
	_ = mime.AddExtensionType(".mjs", "text/javascript; charset=utf-8")
	_ = mime.AddExtensionType(".svg", "image/svg+xml")
	_ = mime.AddExtensionType(".wasm", "application/wasm")
	files := http.FileServer(http.FS(sub))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == marker {
			fmt.Fprint(w, "krazow "+win.ID+" "+version)
			return
		}
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		files.ServeHTTP(w, r)
	})
}

func alreadyOurs(addr string) bool {
	c := http.Client{Timeout: 2 * time.Second}
	r, err := c.Get("http://" + addr + marker)
	if err != nil {
		return false
	}
	defer r.Body.Close()
	buf := make([]byte, 64)
	n, _ := r.Body.Read(buf)
	return strings.HasPrefix(string(buf[:n]), "krazow "+win.ID+" ")
}

func browser() string {
	var c []string
	for _, env := range []string{"ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"} {
		if d := os.Getenv(env); d != "" {
			c = append(c, filepath.Join(d, `Microsoft\Edge\Application\msedge.exe`))
		}
	}
	for _, env := range []string{"ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"} {
		if d := os.Getenv(env); d != "" {
			c = append(c, filepath.Join(d, `Google\Chrome\Application\chrome.exe`))
		}
	}
	for _, p := range c {
		if st, err := os.Stat(p); err == nil && !st.IsDir() {
			return p
		}
	}
	return ""
}

func launch(browserExe, url string) *exec.Cmd {
	profile := filepath.Join(win.DataDir(), "Browser")
	_ = os.MkdirAll(profile, 0o755)
	return exec.Command(browserExe,
		"--app="+url,
		"--user-data-dir="+profile,
		"--no-first-run",
		"--no-default-browser-check",
		"--disable-features=msEdgeSidebarV2,msUndersideButton",
		"--window-size=1100,900",
	)
}

func openDefault(url string) {
	_ = win.Hidden("rundll32.exe", "url.dll,FileProtocolHandler", url)
}

func uninstall() {
	if !win.Ask("Uninstall "+win.AppName+"?",
		"This removes the app and its shortcuts from this computer.",
		"Uninstall", "Cancel") {
		return
	}
	keep := !win.Ask("Also delete "+win.AppName+"'s saved data on this computer?",
		"If you choose Delete, it's gone for good, so make a backup first if the app offers one.\n\n"+
			"Choose Keep to leave it here; it comes back if you install "+win.AppName+" again.",
		"Delete my data", "Keep my data")

	_ = os.Remove(win.StartMenuLink())
	_ = os.Remove(win.DesktopLink())
	_ = win.Hidden("reg.exe", "delete", win.UninstKey, "/f")
	if keep {
		win.Tell(win.AppName+" was uninstalled", "Your data was kept on this computer.")
	} else {
		win.Tell(win.AppName+" was uninstalled", "The app and its data were removed from this computer.")
	}
	rm := `rmdir /s /q "` + win.InstallDir() + `"`
	if !keep {
		rm += ` & rmdir /s /q "` + win.DataDir() + `"`
	}
	_ = startDetached(`cmd.exe /c "ping -n 3 127.0.0.1 >nul & ` + rm + `"`)
}
