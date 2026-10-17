# Run in Windows PowerShell 5.1 on your own Windows installation.
param(
 [string]$OutputPath = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Zorin11-Windows-assets.zip'),
 [switch]$IncludeFonts
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
[StructLayout(LayoutKind.Sequential)] public struct IconSize { public int cx, cy; }
[ComImport, Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IImageFactory { [PreserveSig] int GetImage(IconSize size, uint flags, out IntPtr image); }
[StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] public struct StockIconInfo {
 public uint cbSize; public IntPtr hIcon; public int iSysImageIndex; public int iIcon;
 [MarshalAs(UnmanagedType.ByValTStr,SizeConst=260)] public string szPath;
}
[StructLayout(LayoutKind.Sequential)] public struct BitmapNative { public int type,width,height,widthBytes; public ushort planes,bitsPixel; public IntPtr bits; }
public static class ShellIconExport {
 [DllImport("shell32.dll", CharSet=CharSet.Unicode,PreserveSig=false)] static extern void SHCreateItemFromParsingName(string path,IntPtr ctx,ref Guid iid,[MarshalAs(UnmanagedType.Interface)] out IImageFactory item);
 [DllImport("shell32.dll")] static extern int SHGetStockIconInfo(uint id,uint flags,ref StockIconInfo info);
 [DllImport("shell32.dll", CharSet=CharSet.Unicode)] static extern int SHDefExtractIcon(string path,int index,uint flags,out IntPtr large,out IntPtr small,uint size);
 [DllImport("gdi32.dll")] static extern int GetObject(IntPtr obj,int size,out BitmapNative bmp);
 [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr obj);
 [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr icon);
 public static void Item(string path,string output,int size) {
  Guid iid=typeof(IImageFactory).GUID; IImageFactory item; SHCreateItemFromParsingName(path,IntPtr.Zero,ref iid,out item);
  IntPtr image=IntPtr.Zero;
  try {
   Marshal.ThrowExceptionForHR(item.GetImage(new IconSize{cx=size,cy=size},4,out image));
   BitmapNative bm; GetObject(image,Marshal.SizeOf(typeof(BitmapNative)),out bm);
   if(bm.bits==IntPtr.Zero || bm.bitsPixel!=32) throw new Exception("Shell returned unexpected bitmap");
   using(Bitmap bitmap=new Bitmap(bm.width,bm.height,bm.widthBytes,PixelFormat.Format32bppArgb,bm.bits)) {
    bitmap.RotateFlip(RotateFlipType.RotateNoneFlipY); bitmap.Save(output,ImageFormat.Png);
   }
  } finally { if(image!=IntPtr.Zero)DeleteObject(image);Marshal.ReleaseComObject(item); }
 }
 public static void Stock(uint id,string output,int size) {
  StockIconInfo info=new StockIconInfo();info.cbSize=(uint)Marshal.SizeOf(typeof(StockIconInfo));
  Marshal.ThrowExceptionForHR(SHGetStockIconInfo(id,0,ref info));
  IntPtr big,small;Marshal.ThrowExceptionForHR(SHDefExtractIcon(info.szPath,info.iIcon,0,out big,out small,(uint)size));
  try { using(Icon icon=Icon.FromHandle(big))using(Bitmap bmp=icon.ToBitmap())bmp.Save(output,ImageFormat.Png); }
  finally { if(big!=IntPtr.Zero)DestroyIcon(big);if(small!=IntPtr.Zero)DestroyIcon(small); }
 }
}
'@
$dir = Join-Path $env:TEMP ('Zorin11Assets-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$stock = @{'folder'=3;'drive-harddisk'=8;'drive-harddisk-usb'=7;'computer'=94;'network-workgroup'=18;'user-trash'=31;'text-x-generic'=0}
$items = @{'user-home'=$env:USERPROFILE;'drive-harddisk-root'=($env:SystemDrive+'\');'folder-open'=$env:WINDIR;'system-file-manager'=(Join-Path $env:WINDIR 'explorer.exe');'user-desktop'=[Environment]::GetFolderPath('Desktop');'folder-documents'=[Environment]::GetFolderPath('MyDocuments');'folder-pictures'=[Environment]::GetFolderPath('MyPictures');'folder-music'=[Environment]::GetFolderPath('MyMusic');'folder-videos'=[Environment]::GetFolderPath('MyVideos');'folder-download'=(Join-Path $env:USERPROFILE 'Downloads')}
foreach($size in @(16,24,32,48,64,256)) {
 $sd=Join-Path $dir $size;New-Item -ItemType Directory -Path $sd -Force|Out-Null
 foreach($name in $stock.Keys){[ShellIconExport]::Stock($stock[$name],(Join-Path $sd "$name.png"),$size)}
 foreach($name in $items.Keys){if(Test-Path -LiteralPath $items[$name]){[ShellIconExport]::Item($items[$name],(Join-Path $sd "$name.png"),$size)}}
}
if ($IncludeFonts) {
 $fonts = Join-Path $dir 'fonts'
 New-Item -ItemType Directory -Path $fonts | Out-Null
 foreach ($font in @('segoeui.ttf','SegUIVar.ttf')) {
  $source = Join-Path $env:WINDIR ('Fonts\' + $font)
  if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $fonts }
 }
}
Compress-Archive -Path (Join-Path $dir '*') -DestinationPath $OutputPath -Force
Remove-Item -LiteralPath $dir -Recurse -Force
Write-Output $OutputPath
