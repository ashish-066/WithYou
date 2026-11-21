/**
 * Shared building blocks for the signed-in areas (/app, /platform).
 * Design rules: context/dashboard_rebuild_plan.md, section 2.
 */
export { cx } from './cx';
export { Button, ButtonLink, buttonClass } from './Button';
export { Field, Input, Textarea, Select, Checkbox } from './Field';
export { StatusLabel, type Tone } from './StatusLabel';
export { PageHeader, Section } from './PageHeader';
export { EmptyState, ErrorState, Spinner } from './States';
export { DataTable, Pagination, type Column } from './DataTable';
export { Tabs, type TabItem } from './Tabs';
export { Dialog, Drawer } from './Overlay';
export { ToastProvider, useToast } from './Toast';
export { DefinitionList, CopyField } from './Facts';
export { AppShell, Mark, type Area, type NavGroup, type NavItem } from './AppShell';
