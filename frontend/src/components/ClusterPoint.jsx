import React from "react";

export const ClusterPoint = ({ isCluster, clusterData }) => {
  if (isCluster) {
    return (
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          background: "var(--mt-red, #ED1C24)",
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 13,
          fontWeight: 800,
          cursor: "pointer",
          border: "2px solid #fff",
          boxShadow: "0 2px 6px rgba(0,0,0,0.3)",
        }}
      >
        {clusterData.properties.point_count_abbreviated}
      </div>
    );
  }
  return (
    <div
      style={{
        cursor: "pointer",
        width: 16,
        aspectRatio: 1,
        borderRadius: "50%",
        background: "var(--mt-red, #ED1C24)",
        border: "2px solid #fff",
        boxShadow: "0 1px 4px rgba(0,0,0,0.3)",
      }}
    />
  );
};
