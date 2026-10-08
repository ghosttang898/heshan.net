import { Outlet, useOutletContext } from "react-router-dom";
import AdminSidebar from "./AdminSidebar";
import AdminHeader from "./AdminHeader";
import GeolocationAttribution from "../../components/GeolocationAttribution";

export default function AdminLayout() {
  const user = useOutletContext();
  return <div className="admin-shell"><AdminSidebar user={user} /><div className="admin-workspace">
    <AdminHeader user={user} /><main className="admin-main"><Outlet context={user} /></main>
    <footer className="admin-footer">heshan.net · Created by GhostTang · <GeolocationAttribution /></footer>
  </div></div>;
}
