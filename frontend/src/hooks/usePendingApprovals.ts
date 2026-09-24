"use client";

import { useState, useEffect, useCallback } from 'react';
import { API_URL } from '@/lib/api';

export type PendingOrder = {
    symbol?: string;
    side?: string;
    amount?: number;
    order_type?: string;
    price?: number;
    exchange?: string;
    rationale?: string;
    paper_mode?: boolean;
};

export type PendingApproval = {
    request_id: string;
    kind: string;
    created_at: number;
    expires_at: number;
    order?: PendingOrder;
};

export function usePendingApprovals() {
    const [approvals, setApprovals] = useState<PendingApproval[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchApprovals = useCallback(async () => {
        try {
            const res = await fetch(`${API_URL}/api/pending-approvals`);
            const data = await res.json();
            setApprovals(data.pending || []);
        } catch (err) {
            console.error('Failed to fetch approvals:', err);
        } finally {
            setLoading(false);
        }
    }, []);

    const handleApproval = async (requestId: string, token: string, approve: boolean) => {
        const res = await fetch(`${API_URL}/api/approve-trade`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                request_id: requestId,
                confirm_token: token,
                approve
            })
        });

        // A cancel with a wrong token answers 200 {"ok": false}: read the body, not just the status.
        const body = await res.json().catch(() => ({}));
        if (res.ok && body.ok !== false) {
            fetchApprovals();
            return true;
        }
        return false;
    };

    useEffect(() => {
        fetchApprovals();
        const interval = setInterval(fetchApprovals, 10000);
        return () => clearInterval(interval);
    }, [fetchApprovals]);

    return { approvals, loading, fetchApprovals, handleApproval };
}
