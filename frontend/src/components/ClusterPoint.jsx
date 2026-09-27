import React from "react";

export const ClusterPoint = ({ isCluster, clusterData }) => {
  if (isCluster) {
    return (
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          background: "var(--mgt-blue, #0076bc)",
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 13,
          fontWeight: 800,
          cursor: "pointer",
          border: "2px solid #fff",
          boxShadow: "0 2px 8px rgba(0, 118, 188, 0.45)",
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
        background: "var(--mgt-blue, #0076bc)",
        border: "2px solid #fff",
        boxShadow: "0 1px 6px rgba(0, 118, 188, 0.4)",
      }}
    />
  );
};
