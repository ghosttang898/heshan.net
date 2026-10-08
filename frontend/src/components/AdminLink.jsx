import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCurrentUser } from "../api";
import { getToken, subscribeAuthChange } from "../auth";

export default function AdminLink() {
  const [token, setToken] = useState(getToken());
  const [verified, setVerified] = useState(null);

  useEffect(() => subscribeAuthChange(() => setToken(getToken())), []);
  useEffect(() => {
    let active = true;
    setVerified(null);
    if (token) {
      getCurrentUser().then(({ data }) => {
        if (active) setVerified({ token, role: data.role });
      }).catch(() => { if (active) setVerified(null); });
    }
    return () => { active = false; };
  }, [token]);

  if (!token || verified?.token !== token || !["ADMIN", "SUPER_ADMIN"].includes(verified.role)) return null;
  return <Link to="/admin">管理后台</Link>;
}
