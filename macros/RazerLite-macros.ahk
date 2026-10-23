#Requires AutoHotkey v2.0
#SingleInstance Force
; ============================================================================
;  Macros RazerLite (AutoHotkey v2 : https://www.autohotkey.com)
;  Remplace la partie "macros / remappage" de Synapse.
;  Double-clic pour lancer. Pour l'avoir au démarrage : Win+R, shell:startup,
;  et colle un raccourci vers ce fichier.
;
;  Touches utiles de tes périphériques sans Synapse :
;    Basilisk V3 Pro : XButton1 (arrière), XButton2 (avant),
;                      WheelLeft / WheelRight (molette inclinée)
;    DeathStalker V2 Pro : touches médias et molette de volume (gérées par Windows)
;  Les boutons DPI et le bouton sous le pouce (clutch) sont gérés par la souris
;  elle-même : ils marchent sans rien installer.
; ============================================================================

RazerLiteDir := A_ScriptDir "\.."

; Changer de profil RazerLite depuis le clavier
ApplyProfile(name) {
    global RazerLiteDir
    try Run('pyw -3 -m razerlite apply "' name '"', RazerLiteDir, "Hide")
    catch
        Run('pythonw -m razerlite apply "' name '"', RazerLiteDir, "Hide")
    TrayTip("Profil " name, "RazerLite", 1)
}

^!d:: ApplyProfile("Défaut")   ; Ctrl+Alt+D
^!n:: ApplyProfile("Nuit")     ; Ctrl+Alt+N

; --- Exemples, partout ---------------------------------------------------
; Molette inclinée = changer de bureau virtuel
WheelLeft::  Send("^#{Left}")
WheelRight:: Send("^#{Right}")

; --- Exemples seulement dans un jeu -------------------------------------
; Remplace "jeu.exe" par le nom du .exe (Gestionnaire des tâches > Détails).
#HotIf WinActive("ahk_exe jeu.exe")

; Bouton arrière = rafale de 3 clics
XButton1:: {
    Loop 3 {
        Click()
        Sleep(40)
    }
}

; Bouton avant maintenu = touche Maj maintenue (sprint)
XButton2:: Send("{Shift down}")
XButton2 Up:: Send("{Shift up}")

#HotIf
