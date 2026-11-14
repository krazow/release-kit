// Package win holds the small Windows helpers both programs share.
// The app's identity is set at build time with -ldflags "-X krazow/webapp/internal/win.AppName=..." (see build.sh).
package win

import "strconv"

var (
	AppName   = "App"         // shown in dialogs, shortcuts and Settings → Apps
	ID        = "app"         // folder and registry name, e.g. islandtime or islandtimebeta
	PortText  = "47000"       // fixed, so the app's saved data (stored per web address) is always found again
	HomeURL   = ""            // the app's web address, for Settings → Apps
	Publisher = "krazow"
	Desc      = "An app by krazow"
)

var (
	Port      int
	ExeName   string
	UninstKey string
)

func init() {
	Port, _ = strconv.Atoi(PortText)
	ExeName = ID + ".exe"
	UninstKey = `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\krazow-` + ID
}
