let desktopHidden = false;
export const isPageHidden = () => document.hidden || desktopHidden;
export function setDesktopHidden(value) {
  desktopHidden = value;
  document.dispatchEvent(new Event("visibilitychange"));
}
