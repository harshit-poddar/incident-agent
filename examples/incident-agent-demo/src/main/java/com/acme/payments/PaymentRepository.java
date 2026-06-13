package com.acme.payments;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;

/**
 * Looks up payments for a user. This is the deployed service code the incident
 * agent watches. It ships with a deliberate CWE-89 SQL injection so the
 * security-scan job fails -> the agent is triggered -> the fine-tuned vuln-fixer
 * model proposes the parameterised fix -> a PR is opened (after human approval).
 */
public class PaymentRepository {
    private final Connection connection;

    public PaymentRepository(Connection connection) {
        this.connection = connection;
    }

    public ResultSet findByUser(String userId) throws Exception {
        Statement stmt = connection.createStatement();
        // VULN (CWE-89): untrusted userId concatenated straight into the query.
        String query = "SELECT * FROM payments WHERE user_id = '" + userId + "'";
        return stmt.executeQuery(query);
    }
}
