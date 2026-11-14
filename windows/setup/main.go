// Krazow release kit: Windows setup. Installs the app for the current Windows user (no admin needed),
// adds Start menu and desktop shortcuts, and registers it in Settings → Apps for uninstalling.
// Run with /S to install silently.
package main

import (
	_ "embed"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"krazow/webapp/internal/win"
)

//go:embed payload/app.exe
var appExe []byte

//go:embed payload/app.ico
var appIcon []byte

var version = "dev" // set at build time

func main() {
	silent := false
	for _, a := range os.Args[1:] {
		if s := strings.ToLower(a); s == "/s" || s == "--silent" {
			silent = true
		}
	}
	dir := win.InstallDir()
	exe := filepath.Join(dir, win.ExeName)
	_, err := os.Stat(exe)
	update := err == nil

	if !silent {
		head, body, yes := "Install "+win.AppName+" "+version+"?",
			win.Desc+"\n\nIt's installed for you only (no administrator needed), with shortcuts in the Start menu and on the desktop. "+
				"It opens in its own Microsoft Edge app window and keeps its data on this computer.",
			"Install"
		if update {
			head, body, yes = "Update "+win.AppName+" to "+version+"?",
				"Your data on this computer is kept. If "+win.AppName+" is open, it picks up the update the next time you open it.",
				"Update"
		}
		if !win.Ask(head, body, yes, "Cancel") {
			return
		}
	}
	if err := install(dir, exe); err != nil {
		win.Fail(win.AppName+" couldn't be installed", err.Error())
	}
	if silent {
		return
	}
	head := win.AppName + " is installed"
	if update {
		head = win.AppName + " is up to date"
	}
	if win.Ask(head,
		"Open it from the Start menu or the desktop shortcut. To remove it later: Settings → Apps → Installed apps → "+win.AppName+" → Uninstall.",
		"Open "+win.AppName, "Close") {
		c := exec.Command(exe)
		c.Dir = dir
		_ = c.Start()
	}
}

func install(dir, exe string) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	old := exe + ".old" // a running copy can't be overwritten, but it can be renamed out of the way
	_ = os.Remove(old)
	if _, err := os.Stat(exe); err == nil {
		if err := os.Rename(exe, old); err != nil {
			return fmt.Errorf("close %s and try again (%v)", win.AppName, err)
		}
	}
	tmp := exe + ".new"
	if err := os.WriteFile(tmp, appExe, 0o755); err != nil {
		return err
	}
	if err := os.Rename(tmp, exe); err != nil {
		return err
	}
	_ = os.Remove(old)
	icon := filepath.Join(dir, win.ID+".ico")
	if err := os.WriteFile(icon, appIcon, 0o644); err != nil {
		return err
	}
	_ = os.MkdirAll(filepath.Dir(win.StartMenuLink()), 0o755)
	if err := win.Shortcut(win.StartMenuLink(), exe, icon, win.Desc); err != nil {
		return fmt.Errorf("couldn't make the Start menu shortcut: %v", err)
	}
	_ = win.Shortcut(win.DesktopLink(), exe, icon, win.Desc)

	size := (len(appExe) + len(appIcon)) / 1024
	for _, v := range [][3]string{
		{"DisplayName", "REG_SZ", win.AppName},
		{"DisplayVersion", "REG_SZ", version},
		{"Publisher", "REG_SZ", win.Publisher},
		{"DisplayIcon", "REG_SZ", icon},
		{"InstallLocation", "REG_SZ", dir},
		{"UninstallString", "REG_SZ", `"` + exe + `" --uninstall`},
		{"URLInfoAbout", "REG_SZ", win.HomeURL},
		{"InstallDate", "REG_SZ", time.Now().Format("20060102")},
		{"EstimatedSize", "REG_DWORD", fmt.Sprint(size)},
		{"NoModify", "REG_DWORD", "1"},
		{"NoRepair", "REG_DWORD", "1"},
	} {
		if err := win.RegSet(v[0], v[1], v[2]); err != nil {
			return fmt.Errorf("couldn't register the uninstaller: %v", err)
		}
	}
	return nil
}
