import "./index.css";

import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import ChildSessionPage from "./pages/ChildSessionPage";
import DemoPage from "./pages/DemoPage";
import TherapistDashboard from "./therapist/TherapistDashboard";
import LiveInsightsPage from "./therapist/LiveInsightsPage";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        {/* Child experience */}
        <Route path="/session" element={<ChildSessionPage />} />
        <Route path="/demo" element={<DemoPage />} />

        {/* Therapist area */}
        <Route path="/therapist" element={<TherapistDashboard />} />
        <Route path="/therapist/live" element={<LiveInsightsPage />} />

        {/* Legacy root → child session */}
        <Route path="/" element={<Navigate to="/session" replace />} />

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/session" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
