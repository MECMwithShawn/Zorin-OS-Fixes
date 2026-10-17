local wezterm = require 'wezterm'
local act = wezterm.action
local config = wezterm.config_builder()
config.default_prog = {wezterm.home_dir .. '/.local/bin/pwsh', '-NoLogo'}
config.default_cwd = wezterm.home_dir
config.launch_menu = {
  {label='PowerShell 7', args={wezterm.home_dir .. '/.local/bin/pwsh','-NoLogo'}},
  {label='Bash', args={'/bin/bash','-l'}},
}
config.font = wezterm.font('Cascadia Mono')
config.font_size = 12
config.initial_cols = 120
config.initial_rows = 28
config.window_padding = {left=12,right=12,top=12,bottom=12}
config.enable_wayland = false
config.window_decorations = 'INTEGRATED_BUTTONS|RESIZE'
config.integrated_title_button_style = 'Windows'
config.integrated_title_button_alignment = 'Right'
config.use_fancy_tab_bar = true
config.hide_tab_bar_if_only_one_tab = false
config.tab_max_width = 32
config.show_tab_index_in_tab_bar = false
config.window_background_opacity = 1.0
config.window_frame = {
  font=wezterm.font('Segoe UI'), font_size=10,
  active_titlebar_bg='#202020',inactive_titlebar_bg='#252525',
  active_titlebar_fg='#ffffff',inactive_titlebar_fg='#b0b0b0',
}
config.colors = {
  foreground='#cccccc',background='#0c0c0c',cursor_bg='#ffffff',cursor_fg='#0c0c0c',
  selection_bg='#264f78',selection_fg='#ffffff',split='#424242',
  ansi={'#0c0c0c','#c50f1f','#13a10e','#c19c00','#0037da','#881798','#3a96dd','#cccccc'},
  brights={'#767676','#e74856','#16c60c','#f9f1a5','#3b78ff','#b4009e','#61d6d6','#f2f2f2'},
  tab_bar={
    background='#202020',active_tab={bg_color='#0c0c0c',fg_color='#ffffff'},
    inactive_tab={bg_color='#202020',fg_color='#bdbdbd'},
    inactive_tab_hover={bg_color='#303030',fg_color='#ffffff'},
    new_tab={bg_color='#202020',fg_color='#bdbdbd'},
    new_tab_hover={bg_color='#303030',fg_color='#ffffff'},
  },
}
config.default_cursor_style = 'BlinkingBar'
config.cursor_blink_rate = 600
config.audible_bell = 'Disabled'
config.scrollback_lines = 10000
config.keys = {
  {key='t',mods='CTRL|SHIFT',action=act.SpawnTab 'DefaultDomain'},
  {key='Space',mods='CTRL|SHIFT',action=act.ShowLauncherArgs{flags='FUZZY|LAUNCH_MENU_ITEMS'}},
  {key='p',mods='CTRL|SHIFT',action=act.ActivateCommandPalette},
  {key='d',mods='ALT|SHIFT',action=act.SplitHorizontal{domain='CurrentPaneDomain'}},
  {key='-',mods='ALT|SHIFT',action=act.SplitVertical{domain='CurrentPaneDomain'}},
  {key='w',mods='CTRL|SHIFT',action=act.CloseCurrentPane{confirm=true}},
}
wezterm.on('format-tab-title', function(tab)
  local process = tab.active_pane.foreground_process_name:match('([^/]+)$') or ''
  local title = process=='pwsh' and 'PowerShell' or process=='bash' and 'Bash' or tab.active_pane.title
  return '  '..title..'  '
end)
wezterm.on('format-window-title', function(tab)
  return tab.active_pane.title .. ' — Terminal'
end)
return config
