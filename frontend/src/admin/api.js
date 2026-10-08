import api from "../api";

export const getDashboard = () => api.get("/admin/dashboard");
export const getAdminList = (resource, params) => api.get(`/admin/${resource}`, { params });
export const getAdminDetail = (resource, id) => api.get(`/admin/${resource}/${id}`);
export const setContentStatus = (resource, id, status) => api.patch(`/admin/${resource}/${id}/status`, { status });
export const setUserRole = (id, role, expectedRole) => api.patch(`/admin/users/${id}/role`, { role, expectedRole });
