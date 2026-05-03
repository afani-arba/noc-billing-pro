import React, { createContext, useContext, useState, useEffect } from "react";
import axios from "axios";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(() => localStorage.getItem("noc_field_token") || null);
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem("noc_field_user")); } catch { return null; }
  });

  const login = (newToken, newUser) => {
    localStorage.setItem("noc_field_token", newToken);
    localStorage.setItem("noc_field_user", JSON.stringify(newUser));
    setToken(newToken);
    setUser(newUser);
  };

  const logout = () => {
    localStorage.removeItem("noc_field_token");
    localStorage.removeItem("noc_field_user");
    setToken(null);
    setUser(null);
  };

  // Configure axios defaults
  useEffect(() => {
    if (token) {
      axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    } else {
      delete axios.defaults.headers.common["Authorization"];
    }
  }, [token]);

  return (
    <AuthContext.Provider value={{ token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};
