/** Ícones inline: evita uma dependência só para meia dúzia de SVGs. */

const svg = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
} as const;

export const ArrowUpIcon = () => <svg {...svg}><path d="M12 19V5M5 12l7-7 7 7" /></svg>;
export const BrainIcon = () => <svg {...svg}><path d="M9 3a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 1 5 3 3 0 0 0 4 3 3 3 0 0 0 3-1V5a3 3 0 0 0-3-2z" /><path d="M15 3a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-1 5 3 3 0 0 1-4 3 3 3 0 0 1-3-1V5a3 3 0 0 1 3-2z" /></svg>;
export const CheckIcon = () => <svg {...svg}><path d="m5 13 4 4L19 7" /></svg>;
export const ChevronIcon = () => <svg {...svg}><path d="m9 6 6 6-6 6" /></svg>;
export const ComposeIcon = () => <svg {...svg}><path d="M12 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6" /><path d="M18.4 3.6a2 2 0 0 1 2.8 2.8L13 14.6l-4 1 1-4z" /></svg>;
export const CopyIcon = () => <svg {...svg}><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>;
export const FileIcon = () => <svg {...svg}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></svg>;
export const PencilIcon = () => <svg {...svg}><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z" /></svg>;
export const SidebarIcon = () => <svg {...svg}><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" /></svg>;
export const StopIcon = () => <svg {...svg} fill="currentColor" stroke="none"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>;
export const ThumbDownIcon = () => <svg {...svg}><path d="M17 14V3M7 14l3.5 7a2 2 0 0 0 2-2v-4h5.5a2 2 0 0 0 2-2.4l-1.3-7A2 2 0 0 0 16.7 3H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2z" /></svg>;
export const ThumbUpIcon = () => <svg {...svg}><path d="M7 10v11M17 10l-3.5-7a2 2 0 0 0-2 2v4H6a2 2 0 0 0-2 2.4l1.3 7A2 2 0 0 0 7.3 21H19a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2z" /></svg>;
export const TrashIcon = () => <svg {...svg}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3" /></svg>;
export const XIcon = () => <svg {...svg}><path d="M18 6 6 18M6 6l12 12" /></svg>;
